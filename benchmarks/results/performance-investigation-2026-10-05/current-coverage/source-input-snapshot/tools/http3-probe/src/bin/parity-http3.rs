use std::error::Error;
use std::io::{BufReader, Write};
use std::net::SocketAddr;
use std::sync::Arc;

use bytes::{Buf, Bytes};
use h3_quinn::quinn::{self, rustls};
use http::{header::HeaderName, Request};
use serde_json::{json, Value};

fn report_stream_error() -> std::io::Result<()> {
    writeln!(
        std::io::stdout().lock(),
        "{}",
        json!({
            "stream_reset": true,
            "status": null,
            "content_type": null,
            "body_hex": "",
            "body_stream_error": true
        })
    )
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args().skip(1);
    let address: SocketAddr = args.next().ok_or("missing server address")?.parse()?;
    let certfile = args.next().ok_or("missing trusted certificate")?;
    let specification: Value = serde_json::from_reader(std::io::stdin())?;
    let method = specification["method"]
        .as_str()
        .ok_or("missing request method")?;
    let path = specification["path"]
        .as_str()
        .ok_or("missing request path")?;
    let body_hex = specification["body_hex"]
        .as_str()
        .ok_or("missing request body")?;
    let request_body = decode_hex(body_hex)?;
    let abort_after_body = specification["abort_after_body"].as_bool().unwrap_or(false);
    let abort_response_after_headers = specification["abort_response_after_headers"]
        .as_bool()
        .unwrap_or(false);
    let expect_response_error = specification["expect_response_error"]
        .as_bool()
        .unwrap_or(false);
    let leave_upload_open_until_response = specification["leave_upload_open_until_response"]
        .as_bool()
        .unwrap_or(false);
    let empty_data_frame_before_body = specification["empty_data_frame_before_body"]
        .as_bool()
        .unwrap_or(false);
    let invalid_alpn = specification["invalid_alpn"].as_bool().unwrap_or(false);
    let close_error_code = match specification.get("close_error_code") {
        Some(value) => quinn::VarInt::from_u64(
            value
                .as_u64()
                .ok_or("close_error_code must be a u62 integer")?,
        )?,
        None => quinn::VarInt::from_u32(0),
    };
    let abort_release_file = specification["abort_release_file"].as_str();
    let hold_result_file = specification["hold_result_file"].as_str();
    let hold_release_file = specification["hold_release_file"].as_str();
    let hold_response_stream_for_shutdown = specification["hold_response_stream_for_shutdown"]
        .as_bool()
        .unwrap_or(false);

    let certificate_file = std::fs::File::open(certfile)?;
    let certificates = rustls_pemfile::certs(&mut BufReader::new(certificate_file))
        .collect::<Result<Vec<_>, _>>()?;
    let mut roots = rustls::RootCertStore::empty();
    for certificate in certificates {
        roots.add(certificate)?;
    }
    let mut tls = rustls::ClientConfig::builder()
        .with_root_certificates(roots)
        .with_no_client_auth();
    tls.alpn_protocols = if invalid_alpn {
        vec![b"asgi-parity-invalid".to_vec()]
    } else {
        vec![b"h3".to_vec()]
    };

    let mut endpoint = quinn::Endpoint::client("0.0.0.0:0".parse()?)?;
    let quic_tls = quinn::crypto::rustls::QuicClientConfig::try_from(tls)?;
    endpoint.set_default_client_config(quinn::ClientConfig::new(Arc::new(quic_tls)));
    let connecting = match endpoint.connect(address, "localhost") {
        Ok(connecting) => connecting,
        Err(_error) if expect_response_error => {
            report_stream_error()?;
            return Ok(());
        }
        Err(error) => return Err(error.into()),
    };
    let connection = match connecting.await {
        Ok(connection) => connection,
        Err(_error) if expect_response_error => {
            report_stream_error()?;
            return Ok(());
        }
        Err(error) => return Err(error.into()),
    };
    let _ = writeln!(std::io::stderr().lock(), "HTTP/3 probe: QUIC connected");
    let client_connection = tokio::time::timeout(
        std::time::Duration::from_secs(2),
        h3::client::new(h3_quinn::Connection::new(connection)),
    )
    .await;
    let (mut driver, mut sender) = match client_connection {
        Ok(Ok(connection)) => connection,
        Ok(Err(_error)) if expect_response_error => {
            report_stream_error()?;
            return Ok(());
        }
        Err(_error) if expect_response_error => {
            writeln!(
                std::io::stdout().lock(),
                "{}",
                json!({"response_timeout": true, "status": null})
            )?;
            return Ok(());
        }
        Ok(Err(error)) => return Err(error.into()),
        Err(error) => return Err(error.into()),
    };
    let _ = writeln!(
        std::io::stderr().lock(),
        "HTTP/3 probe: HTTP/3 connection ready"
    );
    tokio::spawn(async move {
        let _ = std::future::poll_fn(|cx| driver.poll_close(cx)).await;
    });

    let uri: http::Uri = format!("https://localhost:{}{}", address.port(), path).parse()?;
    let mut request_builder = Request::builder().method(method).uri(uri);
    let headers = specification["headers"]
        .as_array()
        .ok_or("request headers must be an array")?;
    for header in headers {
        let pair = header.as_array().ok_or("request header must be a pair")?;
        if pair.len() != 2 {
            return Err("request header must contain exactly two values".into());
        }
        let name = pair[0].as_str().ok_or("request header name must be text")?;
        let value = pair[1]
            .as_str()
            .ok_or("request header value must be text")?;
        let name = HeaderName::from_bytes(name.as_bytes())?;
        request_builder = request_builder.header(name, value);
    }
    let has_content_length = headers.iter().any(|header| {
        header
            .as_array()
            .and_then(|pair| pair.first())
            .and_then(Value::as_str)
            .is_some_and(|name| name.eq_ignore_ascii_case("content-length"))
    });
    if !request_body.is_empty() && !has_content_length {
        request_builder = request_builder.header(http::header::CONTENT_LENGTH, request_body.len());
    }
    let request = request_builder.body(())?;
    let send_request = tokio::time::timeout(
        std::time::Duration::from_secs(2),
        sender.send_request(request),
    )
    .await;
    let mut stream = match send_request {
        Ok(Ok(stream)) => stream,
        Ok(Err(_error)) if expect_response_error => {
            report_stream_error()?;
            return Ok(());
        }
        Err(_error) if expect_response_error => {
            writeln!(
                std::io::stdout().lock(),
                "{}",
                json!({"response_timeout": true, "status": null})
            )?;
            return Ok(());
        }
        Ok(Err(error)) => return Err(error.into()),
        Err(error) => return Err(error.into()),
    };
    let _ = writeln!(
        std::io::stderr().lock(),
        "HTTP/3 probe: request headers sent"
    );
    if abort_after_body {
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    }
    if !request_body.is_empty() {
        if empty_data_frame_before_body {
            if let Err(error) = stream.send_data(Bytes::new()).await {
                if expect_response_error {
                    report_stream_error()?;
                    return Ok(());
                }
                return Err(error.into());
            }
        }
        if let Err(error) = stream.send_data(Bytes::from(request_body)).await {
            if expect_response_error {
                report_stream_error()?;
                return Ok(());
            }
            return Err(error.into());
        }
        let _ = writeln!(std::io::stderr().lock(), "HTTP/3 probe: request body sent");
    }
    if abort_after_body {
        if let Some(path) = abort_release_file {
            let path = std::path::Path::new(path);
            let deadline = tokio::time::Instant::now() + std::time::Duration::from_secs(10);
            while !path.exists() {
                if tokio::time::Instant::now() >= deadline {
                    return Err("timed out waiting for the HTTP/3 abort release".into());
                }
                tokio::time::sleep(std::time::Duration::from_millis(10)).await;
            }
        } else {
            tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        }
        stream.stop_stream(h3::error::Code::H3_REQUEST_CANCELLED);
        tokio::time::sleep(std::time::Duration::from_millis(500)).await;
        drop(stream);
        endpoint.close(quinn::VarInt::from_u32(0), b"parity client abort");
        endpoint.wait_idle().await;
        writeln!(std::io::stdout().lock(), "{}", json!({"aborted": true}))?;
        return Ok(());
    }
    if !leave_upload_open_until_response {
        if let Err(error) = stream.finish().await {
            if expect_response_error {
                report_stream_error()?;
                return Ok(());
            }
            return Err(error.into());
        }
    }
    let response_result =
        tokio::time::timeout(std::time::Duration::from_secs(2), stream.recv_response()).await;
    let response = match response_result {
        Ok(Ok(response)) => response,
        Ok(Err(_error)) if expect_response_error => {
            report_stream_error()?;
            return Ok(());
        }
        Err(_error) if expect_response_error => {
            writeln!(
                std::io::stdout().lock(),
                "{}",
                json!({"response_timeout": true, "status": null})
            )?;
            return Ok(());
        }
        Ok(Err(error)) => return Err(error.into()),
        Err(error) => return Err(error.into()),
    };
    let status = response.status().as_u16();
    if abort_response_after_headers {
        stream.stop_sending(h3::error::Code::H3_REQUEST_CANCELLED);
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
        drop(stream);
        drop(sender);
        endpoint.close(quinn::VarInt::from_u32(0), b"parity response abort");
        tokio::time::timeout(std::time::Duration::from_secs(2), endpoint.wait_idle()).await?;
        writeln!(
            std::io::stdout().lock(),
            "{}",
            json!({"status": status, "client_aborted": true})
        )?;
        return Ok(());
    }
    let content_type = response
        .headers()
        .get(http::header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok());
    let mut body = Vec::new();
    let mut body_stream_error = false;
    if hold_response_stream_for_shutdown {
        let Some(mut data) = stream.recv_data().await? else {
            return Err("HTTP/3 shutdown response ended before its first body chunk".into());
        };
        let length = data.remaining();
        body.extend_from_slice(data.chunk());
        data.advance(length);

        let (Some(result_file), Some(release_file)) = (hold_result_file, hold_release_file) else {
            return Err("HTTP/3 held response is missing shutdown synchronization files".into());
        };
        let first_chunk_observation = json!({
            "status": status,
            "content_type": content_type,
            "body_hex": body
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect::<String>(),
            "body_stream_error": false
        });
        std::fs::write(result_file, serde_json::to_vec(&first_chunk_observation)?)?;
        let deadline = tokio::time::Instant::now() + std::time::Duration::from_secs(15);
        while !std::path::Path::new(release_file).exists() {
            if tokio::time::Instant::now() >= deadline {
                return Err("timed out waiting for HTTP/3 response-shutdown release".into());
            }
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        }
        // The server has completed its graceful-shutdown attempt. The case
        // observes the first chunk published above, so do not wait for more
        // response data from the now-stopped server. Closing the QUIC endpoint
        // makes the probe terminate deterministically after the shutdown.
        writeln!(std::io::stdout().lock(), "{}", first_chunk_observation)?;
        endpoint.close(quinn::VarInt::from_u32(0), b"parity server shutdown");
        drop(stream);
        drop(sender);
        tokio::time::timeout(std::time::Duration::from_secs(2), endpoint.wait_idle()).await?;
        return Ok(());
    }
    loop {
        match stream.recv_data().await {
            Ok(Some(mut data)) => {
                let length = data.remaining();
                body.extend_from_slice(data.chunk());
                data.advance(length);
            }
            Ok(None) => break,
            Err(_) => {
                body_stream_error = true;
                break;
            }
        }
    }
    let body_hex = body
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let observation = json!({
        "status": status,
        "content_type": content_type,
        "body_hex": body_hex,
        "body_stream_error": body_stream_error
    });
    if let (Some(result_file), Some(release_file)) = (hold_result_file, hold_release_file) {
        std::fs::write(result_file, serde_json::to_vec(&observation)?)?;
        let deadline = tokio::time::Instant::now() + std::time::Duration::from_secs(15);
        while !std::path::Path::new(release_file).exists() {
            if tokio::time::Instant::now() >= deadline {
                return Err("timed out waiting for the HTTP/3 shutdown release".into());
            }
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        }
    }
    writeln!(std::io::stdout().lock(), "{}", observation)?;
    endpoint.close(close_error_code, b"parity request complete");
    drop(stream);
    drop(sender);
    endpoint.wait_idle().await;
    Ok(())
}

fn decode_hex(value: &str) -> Result<Vec<u8>, Box<dyn Error>> {
    if value.len() % 2 != 0 {
        return Err("request body hex must have an even number of digits".into());
    }
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let digits = std::str::from_utf8(pair)?;
            Ok(u8::from_str_radix(digits, 16)?)
        })
        .collect()
}
