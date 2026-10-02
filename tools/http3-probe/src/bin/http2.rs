use std::error::Error;
use std::future::poll_fn;
use std::io::BufReader;
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::{Duration, Instant};

use bytes::Bytes;
use h2::client::SendRequest;
use http::{Request, Uri};
use serde_json::{json, Value};
use tokio::net::TcpStream;
use tokio::time::{sleep, timeout};
use tokio_rustls::rustls::{self, pki_types::ServerName};
use tokio_rustls::TlsConnector;

type BenchError = Box<dyn Error + Send + Sync>;

fn percentile(values: &[f64], p: f64) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let index = ((p * values.len() as f64).ceil() as usize).saturating_sub(1);
    values[index.min(values.len() - 1)]
}

fn expected_body(config: &Value) -> Result<Vec<u8>, BenchError> {
    if let Some(size) = config.get("response_bytes").and_then(Value::as_u64) {
        return Ok(vec![b'x'; size as usize]);
    }
    if let Some(body) = config.get("expected_body").and_then(Value::as_str) {
        return Ok(body.as_bytes().to_vec());
    }
    let mode = config.get("mode").and_then(Value::as_str).unwrap_or("fixed");
    let body = match mode {
        "upload" => format!(
            "bytes={}",
            config.get("upload_bytes").and_then(Value::as_u64).unwrap_or(0)
        )
        .into_bytes(),
        "scope" => b"scope-ok".to_vec(),
        "context" => b"request-context".to_vec(),
        "exception" => b"Internal Server Error".to_vec(),
        _ => b"Hello World!".to_vec(),
    };
    Ok(body)
}

async fn request_once(
    sender: &mut SendRequest<Bytes>,
    uri: &Uri,
    config: &Value,
    expected: &[u8],
    upload_body: &[u8],
) -> Result<(u16, usize, usize), BenchError> {
    *sender = sender.clone().ready().await?;
    let upload_bytes = upload_body.len();
    let method = if upload_bytes == 0 { "GET" } else { "POST" };
    let mut builder = Request::builder().method(method).uri(uri.clone());
    if upload_bytes > 0 {
        builder = builder.header("content-length", upload_bytes.to_string());
    }
    builder = builder.header("user-agent", "uvicorn-rs-native-h2-benchmark/1");
    if let Some(headers) = config.get("headers").and_then(Value::as_array) {
        for pair in headers {
            if let (Some(name), Some(value)) = (
                pair.as_array().and_then(|pair| pair.first()).and_then(Value::as_str),
                pair.as_array().and_then(|pair| pair.get(1)).and_then(Value::as_str),
            ) {
                builder = builder.header(name, value);
            }
        }
    }
    let request = builder.body(())?;
    let (response_future, mut request_stream) = sender.send_request(request, upload_bytes == 0)?;

    if upload_bytes > 0 {
        let chunk_size = config
            .get("upload_chunk_bytes")
            .and_then(Value::as_u64)
            .unwrap_or(65_536) as usize;
        let mut offset = 0;
        while offset < upload_bytes {
            let wanted = chunk_size.min(upload_bytes - offset);
            request_stream.reserve_capacity(wanted);
            let capacity = poll_fn(|cx| request_stream.poll_capacity(cx))
                .await
                .ok_or("HTTP/2 upload stream closed before the request body finished")??;
            let length = capacity.min(wanted);
            let end_stream = offset + length == upload_bytes;
            request_stream.send_data(
                Bytes::copy_from_slice(&upload_body[offset..offset + length]),
                end_stream,
            )?;
            offset += length;
        }
    }

    let response = response_future.await?;
    let status = response.status().as_u16();
    let mut response_body = response.into_body();
    let mut offset = 0;
    let mut response_bytes = 0;
    let mut response_data_frames = 0;
    let read_rate = config
        .get("read_rate_bytes_per_second")
        .and_then(Value::as_u64)
        .unwrap_or(0);
    let pacing_started = Instant::now();
    while let Some(chunk) = response_body.data().await {
        let chunk = chunk?;
        response_data_frames += 1;
        let end = offset + chunk.len();
        if end > expected.len() || chunk.as_ref() != &expected[offset..end] {
            return Err("HTTP/2 response body differs from the expected bytes".into());
        }
        offset = end;
        response_bytes += chunk.len();
        if read_rate > 0 {
            let target_elapsed = Duration::from_secs_f64(offset as f64 / read_rate as f64);
            let elapsed = pacing_started.elapsed();
            if target_elapsed > elapsed {
                sleep(target_elapsed - elapsed).await;
            }
        }
        response_body.flow_control().release_capacity(chunk.len())?;
    }
    if offset != expected.len() {
        return Err(format!(
            "HTTP/2 response body length {offset} did not match expected {}",
            expected.len()
        )
        .into());
    }
    Ok((status, response_bytes, response_data_frames))
}

async fn connect_h2(
    host: &str,
    port: u16,
    connector: &TlsConnector,
) -> Result<SendRequest<Bytes>, BenchError> {
    let socket = TcpStream::connect(SocketAddr::new(host.parse()?, port)).await?;
    let tls = connector
        .connect(ServerName::try_from("localhost")?, socket)
        .await?;
    if tls.get_ref().1.alpn_protocol() != Some(b"h2".as_slice()) {
        return Err("TLS did not negotiate HTTP/2 with ALPN".into());
    }
    let (sender, connection) = h2::client::handshake(tls).await?;
    tokio::spawn(async move {
        let _ = connection.await;
    });
    Ok(sender)
}

async fn run(config: Value) -> Result<Value, BenchError> {
    let host = config.get("host").and_then(Value::as_str).unwrap_or("127.0.0.1");
    let port = config.get("port").and_then(Value::as_u64).ok_or("missing port")? as u16;
    let cert_path = config.get("certfile").and_then(Value::as_str).ok_or("missing certfile")?;
    let seconds = config.get("seconds").and_then(Value::as_f64).ok_or("missing duration")?;
    let concurrency = config.get("concurrency").and_then(Value::as_u64).unwrap_or(1) as usize;
    let connections = config
        .get("connections")
        .and_then(Value::as_u64)
        .unwrap_or(4)
        .max(1)
        .min(concurrency.max(1) as u64) as usize;
    let expected_status = config.get("expected_status").and_then(Value::as_u64).unwrap_or(200) as u16;
    let path = config.get("path").and_then(Value::as_str).unwrap_or("/fixed");
    let uri: Uri = format!("https://localhost:{port}{path}").parse()?;
    let expected = Arc::new(expected_body(&config)?);
    let upload_size = config.get("upload_bytes").and_then(Value::as_u64).unwrap_or(0) as usize;
    let upload_body = Arc::new(vec![b'a'; upload_size]);
    let started = Instant::now();

    let cert_file = std::fs::File::open(cert_path)?;
    let certs = rustls_pemfile::certs(&mut BufReader::new(cert_file))
        .collect::<Result<Vec<_>, _>>()?;
    let mut roots = rustls::RootCertStore::empty();
    for cert in certs {
        roots.add(cert)?;
    }
    let mut tls_config = rustls::ClientConfig::builder()
        .with_root_certificates(roots)
        .with_no_client_auth();
    tls_config.alpn_protocols = vec![b"h2".to_vec()];
    let connector = TlsConnector::from(Arc::new(tls_config));
    let mut senders = Vec::with_capacity(connections);
    for _ in 0..connections {
        senders.push(connect_h2(host, port, &connector).await?);
    }

    let deadline = Instant::now() + Duration::from_secs_f64(seconds);
    let request_timeout = Duration::from_secs(10);
    let workers = (0..concurrency).map(|worker_index| {
        let mut sender = senders[worker_index % senders.len()].clone();
        let uri = uri.clone();
        let expected = Arc::clone(&expected);
        let upload_body = Arc::clone(&upload_body);
        let config = config.clone();
        async move {
            let mut latencies = Vec::new();
            let mut response_bytes = 0_u64;
            let mut request_bytes = 0_u64;
            let mut response_data_frames = 0_u64;
            let mut failures = Vec::new();
            while Instant::now() < deadline {
                let request_started = Instant::now();
                let outcome = timeout(
                    request_timeout,
                    request_once(&mut sender, &uri, &config, &expected, &upload_body),
                )
                .await;
                let (status, received, data_frames) = match outcome {
                    Ok(Ok(result)) => result,
                    Ok(Err(error)) => {
                        failures.push(error.to_string());
                        break;
                    }
                    Err(_) => {
                        failures.push("HTTP/2 request timed out waiting for a complete response".into());
                        break;
                    }
                };
                if status != expected_status {
                    failures.push(format!(
                        "unexpected HTTP status {status} (wanted {expected_status})"
                    ));
                    break;
                }
                request_bytes += upload_body.len() as u64;
                response_bytes += received as u64;
                response_data_frames += data_frames as u64;
                latencies.push(request_started.elapsed().as_secs_f64() * 1000.0);
            }
            (latencies, request_bytes, response_bytes, response_data_frames, failures)
        }
    });
    let results = futures_util::future::join_all(workers).await;
    let elapsed = started.elapsed().as_secs_f64();
    let mut latencies = Vec::new();
    let mut request_bytes = 0_u64;
    let mut response_bytes = 0_u64;
    let mut response_data_frames = 0_u64;
    let mut failures = Vec::new();
    for (worker_latencies, sent, received, worker_data_frames, worker_failures) in results {
        latencies.extend(worker_latencies);
        request_bytes += sent;
        response_bytes += received;
        response_data_frames += worker_data_frames;
        failures.extend(worker_failures);
    }
    latencies.sort_by(f64::total_cmp);
    let requests = latencies.len();
    Ok(json!({
        "requests": requests,
        "duration_seconds": elapsed,
        "requests_per_second": requests as f64 / elapsed,
        "request_body_bytes": request_bytes,
        "response_body_bytes": response_bytes,
        "response_data_frames": response_data_frames,
        "application_bytes_per_second": (request_bytes + response_bytes) as f64 / elapsed,
        "p50_ms": percentile(&latencies, 0.50),
        "p95_ms": percentile(&latencies, 0.95),
        "p99_ms": percentile(&latencies, 0.99),
        "failures": failures.len(),
        "first_failure": failures.first().map(|failure| json!({ "error": failure })),
        "protocol": "h2 (TLS ALPN verified)",
        "connections": connections,
        "streams_per_connection_target": concurrency.div_ceil(connections),
    }))
}

#[tokio::main]
async fn main() -> Result<(), BenchError> {
    let input = std::env::args().nth(1).ok_or("missing JSON client config")?;
    let config: Value = serde_json::from_str(&input)?;
    let result = run(config).await?;
    println!("{}", serde_json::to_string(&result)?);
    if result.get("failures").and_then(Value::as_u64).unwrap_or(0) > 0
        || result.get("requests").and_then(Value::as_u64).unwrap_or(0) == 0
    {
        return Err("HTTP/2 benchmark correctness gate failed".into());
    }
    Ok(())
}
