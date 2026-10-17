use std::error::Error;
use std::io::Write;
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::{Duration, Instant};

use bytes::{Buf, Bytes};
use futures_util::future::join_all;
use h3_quinn::quinn::{self, rustls};
use http::Request;

type BenchError = Box<dyn Error + Send + Sync>;

fn percentile(values: &[f64], p: f64) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let index = ((p * values.len() as f64).ceil() as usize).saturating_sub(1);
    values[index.min(values.len() - 1)]
}

#[tokio::main]
async fn main() -> Result<(), BenchError> {
    let mut args = std::env::args().skip(1);
    let address: SocketAddr = args.next().ok_or("missing server address")?.parse()?;
    let certfile = args.next().ok_or("missing CA certificate")?;
    let seconds: f64 = args.next().ok_or("missing duration seconds")?.parse()?;
    let concurrency: usize = args.next().ok_or("missing concurrency")?.parse()?;
    let requested_connections: usize = args
        .next()
        .ok_or("missing QUIC connection count")?
        .parse()?;
    let connection_count = requested_connections.min(concurrency).max(1);
    let mode = args.next().ok_or("missing mode")?;
    let path = args.next().ok_or("missing path")?;
    let response_bytes: usize = args.next().ok_or("missing response bytes")?.parse()?;
    let upload_bytes: usize = args.next().ok_or("missing upload bytes")?.parse()?;
    let expected_status: u16 = args.next().ok_or("missing expected status")?.parse()?;
    let expected_override = args.next().unwrap_or_default();
    let read_rate_bytes_per_second: u64 = args.next().unwrap_or_else(|| "0".to_string()).parse()?;
    let h3_grease: bool = args.next().unwrap_or_else(|| "true".to_string()).parse()?;
    let request_body_bytes: usize = args.next().unwrap_or_else(|| "0".to_string()).parse()?;

    let expected_body = if response_bytes > 0 {
        vec![b'x'; response_bytes]
    } else if !expected_override.is_empty() {
        expected_override.into_bytes()
    } else if mode == "upload" {
        format!("bytes={upload_bytes}").into_bytes()
    } else if mode == "scope" {
        b"scope-ok".to_vec()
    } else if mode == "context" {
        b"request-context".to_vec()
    } else if mode == "exception" {
        b"Internal Server Error".to_vec()
    } else {
        b"Hello World!".to_vec()
    };
    let expected_body = Arc::new(expected_body);
    let upload_chunks = Arc::new(
        (0..upload_bytes.div_ceil(65_536))
            .map(|index| {
                let remaining = upload_bytes - index * 65_536;
                Bytes::from(vec![b'a'; remaining.min(65_536)])
            })
            .collect::<Vec<_>>(),
    );
    let request_body = Arc::new(Bytes::from(vec![b'a'; request_body_bytes]));

    let cert_file = std::fs::File::open(certfile)?;
    let certs = rustls_pemfile::certs(&mut std::io::BufReader::new(cert_file))
        .collect::<Result<Vec<_>, _>>()?;
    let mut roots = rustls::RootCertStore::empty();
    for cert in certs {
        roots.add(cert)?;
    }
    let mut tls = rustls::ClientConfig::builder()
        .with_root_certificates(roots)
        .with_no_client_auth();
    tls.alpn_protocols = vec![b"h3".to_vec()];

    let mut endpoint = quinn::Endpoint::client("0.0.0.0:0".parse()?)?;
    let quic_tls = quinn::crypto::rustls::QuicClientConfig::try_from(tls)?;
    endpoint.set_default_client_config(quinn::ClientConfig::new(Arc::new(quic_tls)));
    let mut senders = Vec::with_capacity(connection_count);
    for _ in 0..connection_count {
        let connection = endpoint.connect(address, "localhost")?.await?;
        let (mut driver, sender) = h3::client::builder()
            .send_grease(h3_grease)
            .build::<_, _, Bytes>(h3_quinn::Connection::new(connection))
            .await?;
        tokio::spawn(async move {
            let _ = std::future::poll_fn(|cx| driver.poll_close(cx)).await;
        });
        senders.push(sender);
    }

    let uri = format!("https://localhost:{}{}", address.port(), path);
    let deadline = Instant::now() + Duration::from_secs_f64(seconds);
    let started = Instant::now();
    let workers =
        (0..concurrency).map(|worker_index| {
            let mut request_sender = senders[worker_index % connection_count].clone();
            let uri = uri.clone();
            let expected_body = Arc::clone(&expected_body);
            let upload_chunks = Arc::clone(&upload_chunks);
            let request_body = Arc::clone(&request_body);
            async move {
                let mut latencies = Vec::new();
                let mut response_bytes = 0_u64;
                let mut response_data_chunks = 0_u64;
                let mut request_bytes = 0_u64;
                let mut failure = None;
                while Instant::now() < deadline {
                    let request_started = Instant::now();
                    // RFC 9110 gives GET content no generally defined semantics
                    // and advises clients not to send it without prior agreement.
                    // Use POST for every workload that intentionally sends content.
                    let method = if upload_bytes > 0 || request_body_bytes > 0 {
                        "POST"
                    } else {
                        "GET"
                    };
                    let request_builder = Request::builder().method(method).uri(&uri);
                    // RFC 9110 §8.6 says a sender SHOULD NOT include
                    // Content-Length when a request has no content and its
                    // method semantics do not anticipate content. Keep the
                    // field only for the POST workloads that send a body.
                    let request_builder = if upload_bytes > 0 || request_body_bytes > 0 {
                        let content_length = if upload_bytes > 0 {
                            upload_bytes.to_string()
                        } else {
                            request_body_bytes.to_string()
                        };
                        request_builder.header("content-length", content_length)
                    } else {
                        request_builder
                    };
                    let request = match request_builder.body(()) {
                        Ok(request) => request,
                        Err(error) => {
                            failure = Some(error.to_string());
                            break;
                        }
                    };
                    let mut stream = match request_sender.send_request(request).await {
                        Ok(stream) => stream,
                        Err(error) => {
                            failure = Some(format!("H3 request failed: {error}"));
                            break;
                        }
                    };
                    if upload_bytes > 0 {
                        for chunk in upload_chunks.iter() {
                            if let Err(error) = stream.send_data(chunk.clone()).await {
                                failure = Some(format!("H3 upload failed: {error}"));
                                break;
                            }
                            request_bytes += chunk.len() as u64;
                        }
                        if failure.is_some() {
                            break;
                        }
                    } else if request_body_bytes > 0 {
                        if let Err(error) = stream.send_data(request_body.as_ref().clone()).await {
                            failure = Some(format!("H3 request body failed: {error}"));
                            break;
                        }
                        request_bytes += request_body_bytes as u64;
                    }
                    if let Err(error) = stream.finish().await {
                        failure = Some(format!("H3 request finish failed: {error}"));
                        break;
                    }
                    let response =
                        match tokio::time::timeout(Duration::from_secs(5), stream.recv_response())
                            .await
                        {
                            Ok(Ok(response)) => response,
                            Ok(Err(error)) => {
                                failure = Some(format!("H3 response headers failed: {error}"));
                                break;
                            }
                            Err(_) => {
                                failure =
                                    Some("timed out waiting for H3 response headers".to_string());
                                break;
                            }
                        };
                    if response.status().as_u16() != expected_status {
                        failure = Some(format!(
                            "unexpected HTTP status {} (wanted {})",
                            response.status(),
                            expected_status
                        ));
                    }
                    let response_status = response.status();
                    let declared_content_length = response
                        .headers()
                        .get("content-length")
                        .map(|value| value.to_str().unwrap_or("<invalid>").to_owned());
                    let request_index = latencies.len() + 1;
                    let mut offset = 0_usize;
                    let mut request_data_chunks = 0_u64;
                    let pacing_started = Instant::now();
                    loop {
                        let mut data =
                            match tokio::time::timeout(Duration::from_secs(5), stream.recv_data())
                                .await
                            {
                                Ok(Ok(Some(data))) => data,
                                Ok(Ok(None)) => break,
                                Ok(Err(error)) => {
                                    failure = Some(format!("H3 response body failed: {error}"));
                                    break;
                                }
                                Err(_) => {
                                    failure =
                                        Some("timed out waiting for H3 response body".to_string());
                                    break;
                                }
                            };
                        let length = data.remaining();
                        response_data_chunks += 1;
                        request_data_chunks += 1;
                        if offset + length > expected_body.len()
                            || data.chunk() != &expected_body[offset..offset + length]
                        {
                            failure = Some("response body differs from expected bytes".to_string());
                        }
                        offset += length;
                        response_bytes += length as u64;
                        if read_rate_bytes_per_second > 0 {
                            let target_elapsed = Duration::from_secs_f64(
                                offset as f64 / read_rate_bytes_per_second as f64,
                            );
                            let elapsed = pacing_started.elapsed();
                            if target_elapsed > elapsed {
                                tokio::time::sleep(target_elapsed - elapsed).await;
                            }
                        }
                        data.advance(length);
                    }
                    if offset != expected_body.len() {
                        failure = Some(format!(
                            "response body length {} did not match expected {} (request={}, status={}, content-length={:?}, data_chunks={})",
                            offset,
                            expected_body.len(),
                            request_index,
                            response_status,
                            declared_content_length,
                            request_data_chunks
                        ));
                    }
                    if failure.is_some() {
                        break;
                    }
                    latencies.push(request_started.elapsed().as_secs_f64() * 1000.0);
                }
                (
                    latencies,
                    request_bytes,
                    response_bytes,
                    response_data_chunks,
                    failure,
                )
            }
        });
    let results = join_all(workers).await;
    let elapsed = started.elapsed().as_secs_f64();
    let mut latencies = Vec::new();
    let mut request_bytes = 0_u64;
    let mut response_bytes = 0_u64;
    let mut response_data_chunks = 0_u64;
    let mut failures = Vec::new();
    for (worker_latencies, sent, received, worker_data_chunks, failure) in results {
        latencies.extend(worker_latencies);
        request_bytes += sent;
        response_bytes += received;
        response_data_chunks += worker_data_chunks;
        if let Some(failure) = failure {
            failures.push(failure);
        }
    }
    latencies.sort_by(f64::total_cmp);
    let requests = latencies.len();
    writeln!(
        std::io::stdout().lock(),
        "{{\"h3_grease\":{h3_grease},\"requests\":{requests},\"duration_seconds\":{elapsed:.9},\"requests_per_second\":{:.3},\"request_body_bytes\":{request_bytes},\"response_body_bytes\":{response_bytes},\"response_data_chunks\":{response_data_chunks},\"application_bytes_per_second\":{:.3},\"p50_ms\":{:.6},\"p95_ms\":{:.6},\"p99_ms\":{:.6},\"failures\":{},\"first_failure\":{}}}",
        requests as f64 / elapsed,
        (request_bytes + response_bytes) as f64 / elapsed,
        percentile(&latencies, 0.50),
        percentile(&latencies, 0.95),
        percentile(&latencies, 0.99),
        failures.len(),
        failures
            .first()
            .map(|reason| format!("\"{}\"", reason.replace('"', "\\\"")))
            .unwrap_or_else(|| "null".to_string())
    )?;
    drop(senders);
    // RFC 9114: an HTTP/3 application close without an error uses H3_NO_ERROR.
    endpoint.close(quinn::VarInt::from_u32(0x100), b"benchmark complete");
    endpoint.wait_idle().await;
    if !failures.is_empty() || requests == 0 {
        return Err("HTTP/3 benchmark correctness gate failed".into());
    }
    Ok(())
}
