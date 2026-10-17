use std::error::Error;
use std::io::{BufReader, Write};
use std::net::SocketAddr;
use std::sync::Arc;

use bytes::{Buf, Bytes};
use h3_quinn::quinn::{self, rustls};
use http::{header::HeaderName, HeaderMap, HeaderValue, Request};
use serde_json::{json, Value};

async fn send_truncated_data_frame(
    connection: &quinn::Connection,
    authority: &str,
    path: &str,
) -> Result<quinn::RecvStream, Box<dyn Error>> {
    let mut field_section = vec![
        0x00, // required insert count
        0x00, // delta base
        0xd4, // static :method POST
        0xd7, // static :scheme https
    ];
    if path.len() >= 127 || authority.len() >= 127 {
        return Err("malformed HTTP/3 probe authority/path is too long".into());
    }
    // QPACK literal without a name reference (:path), followed by a literal
    // value. The short test path keeps both string lengths single-byte.
    field_section.push(0x20 | u8::try_from(b":path".len())?);
    field_section.extend_from_slice(b":path");
    field_section.push(u8::try_from(path.len())?);
    field_section.extend_from_slice(path.as_bytes());
    // QPACK literal with a static name reference to :authority (index zero).
    field_section.push(0x50);
    field_section.push(u8::try_from(authority.len())?);
    field_section.extend_from_slice(authority.as_bytes());
    if field_section.len() >= 64 {
        return Err("malformed HTTP/3 probe header block exceeds one-byte frame length".into());
    }

    let (mut send, receive) = connection.open_bi().await?;
    let mut wire = Vec::with_capacity(field_section.len() + 5);
    wire.push(0x01); // HEADERS frame
    wire.push(u8::try_from(field_section.len())?);
    wire.extend_from_slice(&field_section);
    wire.extend_from_slice(&[0x00, 0x01]); // DATA frame declares one byte
                                           // Deliberately omit the declared DATA byte, then cleanly FIN the request
                                           // stream. This is the minimal input that distinguishes empty DATA from a
                                           // truncated DATA frame in h3 0.0.8.
    send.write_all(&wire).await?;
    send.finish()?;
    Ok(receive)
}

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

fn sequence_stage_error(
    request_index: usize,
    stage: &str,
    error: impl std::fmt::Display,
) -> Box<dyn Error> {
    std::io::Error::other(format!(
        "HTTP/3 sequence request {request_index} {stage} failed: {error}"
    ))
    .into()
}

async fn sequence_response(
    sender: &mut h3::client::SendRequest<h3_quinn::OpenStreams, Bytes>,
    address: SocketAddr,
    specification: &Value,
    request_index: usize,
) -> Result<Value, Box<dyn Error>> {
    let method = specification["method"]
        .as_str()
        .ok_or("missing sequence method")?;
    let path = specification["path"]
        .as_str()
        .ok_or("missing sequence path")?;
    let body = decode_hex(
        specification["body_hex"]
            .as_str()
            .ok_or("missing sequence body")?,
    )?;
    let mut builder = Request::builder().method(method).uri(format!(
        "https://localhost:{}{}",
        address.port(),
        path
    ));
    let headers = specification["headers"]
        .as_array()
        .ok_or("missing sequence headers")?;
    for header in headers {
        let pair = header.as_array().ok_or("sequence header must be a pair")?;
        if pair.len() != 2 {
            return Err("sequence header must contain exactly two values".into());
        }
        let name = pair[0]
            .as_str()
            .ok_or("sequence header name must be text")?;
        let value = pair[1]
            .as_str()
            .ok_or("sequence header value must be text")?;
        builder = builder.header(HeaderName::from_bytes(name.as_bytes())?, value);
    }
    if !body.is_empty()
        && !headers.iter().any(|header| {
            header[0]
                .as_str()
                .is_some_and(|name| name.eq_ignore_ascii_case("content-length"))
        })
    {
        builder = builder.header(http::header::CONTENT_LENGTH, body.len());
    }
    let mut stream = tokio::time::timeout(
        std::time::Duration::from_secs(2),
        sender.send_request(builder.body(())?),
    )
    .await
    .map_err(|error| sequence_stage_error(request_index, "open-stream deadline", error))?
    .map_err(|error| sequence_stage_error(request_index, "open-stream", error))?;
    if !body.is_empty() {
        stream
            .send_data(Bytes::from(body))
            .await
            .map_err(|error| sequence_stage_error(request_index, "send-body", error))?;
    }
    stream
        .finish()
        .await
        .map_err(|error| sequence_stage_error(request_index, "finish-upload", error))?;
    let response = tokio::time::timeout(std::time::Duration::from_secs(2), stream.recv_response())
        .await
        .map_err(|error| sequence_stage_error(request_index, "receive-headers deadline", error))?
        .map_err(|error| sequence_stage_error(request_index, "receive-headers", error))?;
    let content_type = response
        .headers()
        .get(http::header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok());
    let mut response_body = Vec::new();
    while let Some(mut data) =
        tokio::time::timeout(std::time::Duration::from_secs(2), stream.recv_data())
            .await
            .map_err(|error| sequence_stage_error(request_index, "receive-body deadline", error))?
            .map_err(|error| sequence_stage_error(request_index, "receive-body", error))?
    {
        let length = data.remaining();
        response_body.extend_from_slice(data.chunk());
        data.advance(length);
    }
    Ok(json!({
        "status": response.status().as_u16(),
        "content_type": content_type,
        "body_hex": response_body.iter().map(|byte| format!("{byte:02x}")).collect::<String>(),
        "body_stream_error": false,
        "stream_reset": false
    }))
}

async fn hold_sequence_connection(
    connection: &quinn::Connection,
    specification: &Value,
    responses: &[Value],
) -> Result<(), Box<dyn Error>> {
    let result_file = specification["hold_result_file"]
        .as_str()
        .ok_or("request sequence is missing its result synchronization file")?;
    let release_file = specification["hold_release_file"]
        .as_str()
        .ok_or("request sequence is missing its release synchronization file")?;
    let temporary_result =
        std::path::Path::new(result_file).with_extension("http3-sequence-result.partial");
    std::fs::write(
        &temporary_result,
        serde_json::to_vec(&json!({"responses": responses}))?,
    )?;
    std::fs::rename(temporary_result, result_file)?;
    // Keep the original connection alive while the observer examines the
    // completed prefix. No later request starts until it releases this barrier.
    let deadline = tokio::time::Instant::now() + std::time::Duration::from_secs(15);
    while !std::path::Path::new(release_file).exists() {
        if let Some(error) = connection.close_reason() {
            return Err(format!("HTTP/3 peer closed before sequence release: {error}").into());
        }
        if tokio::time::Instant::now() >= deadline {
            return Err("timed out waiting for HTTP/3 sequence release".into());
        }
        tokio::time::sleep(std::time::Duration::from_millis(10)).await;
    }
    if let Some(error) = connection.close_reason() {
        return Err(format!("HTTP/3 peer closed before sequence release: {error}").into());
    }
    Ok(())
}

async fn request_sequence(
    sender: &mut h3::client::SendRequest<h3_quinn::OpenStreams, Bytes>,
    endpoint: &quinn::Endpoint,
    connection: &quinn::Connection,
    address: SocketAddr,
    specification: &Value,
) -> Result<(), Box<dyn Error>> {
    if specification
        .get("concurrent")
        .and_then(Value::as_bool)
        .unwrap_or(false)
    {
        return concurrent_request_sequence(sender, endpoint, connection, address, specification)
            .await;
    }
    let requests = specification["request_sequence"]
        .as_array()
        .ok_or("request_sequence must be an array")?;
    if !(2..=128).contains(&requests.len()) {
        return Err("request_sequence requires between two and 128 requests".into());
    }
    let hold_after_response = specification["hold_after_response"]
        .as_u64()
        .and_then(|index| usize::try_from(index).ok())
        .filter(|index| (1..=requests.len()).contains(index))
        .ok_or("hold_after_response must select a declared request")?;
    let mut responses = Vec::with_capacity(requests.len());
    for (index, request) in requests.iter().enumerate() {
        responses.push(sequence_response(sender, address, request, index + 1).await?);
        if index + 1 == hold_after_response {
            hold_sequence_connection(connection, specification, &responses).await?;
        }
    }
    let observation = json!({"responses": responses});
    writeln!(std::io::stdout().lock(), "{}", observation)?;
    endpoint.close(
        quinn::VarInt::from_u32(0x100),
        b"parity request sequence complete",
    );
    Ok(())
}

async fn concurrent_request_sequence(
    sender: &mut h3::client::SendRequest<h3_quinn::OpenStreams, Bytes>,
    endpoint: &quinn::Endpoint,
    connection: &quinn::Connection,
    address: SocketAddr,
    specification: &Value,
) -> Result<(), Box<dyn Error>> {
    let requests = specification["request_sequence"]
        .as_array()
        .ok_or("request_sequence must be an array")?;
    if !(2..=128).contains(&requests.len()) {
        return Err("request_sequence requires between two and 128 requests".into());
    }
    let mut streams = Vec::with_capacity(requests.len());
    for (index, request) in requests.iter().enumerate() {
        let method = request["method"]
            .as_str()
            .ok_or("missing sequence method")?;
        let path = request["path"].as_str().ok_or("missing sequence path")?;
        let body = decode_hex(
            request["body_hex"]
                .as_str()
                .ok_or("missing sequence body")?,
        )?;
        let mut builder = Request::builder().method(method).uri(format!(
            "https://localhost:{}{}",
            address.port(),
            path
        ));
        let headers = request["headers"]
            .as_array()
            .ok_or("missing sequence headers")?;
        for header in headers {
            let pair = header.as_array().ok_or("sequence header must be a pair")?;
            if pair.len() != 2 {
                return Err("sequence header must contain exactly two values".into());
            }
            let name = pair[0]
                .as_str()
                .ok_or("sequence header name must be text")?;
            let value = pair[1]
                .as_str()
                .ok_or("sequence header value must be text")?;
            builder = builder.header(HeaderName::from_bytes(name.as_bytes())?, value);
        }
        if !body.is_empty()
            && !headers.iter().any(|header| {
                header[0]
                    .as_str()
                    .is_some_and(|name| name.eq_ignore_ascii_case("content-length"))
            })
        {
            builder = builder.header(http::header::CONTENT_LENGTH, body.len());
        }
        let mut stream = tokio::time::timeout(
            std::time::Duration::from_secs(2),
            sender.send_request(builder.body(())?),
        )
        .await
        .map_err(|error| sequence_stage_error(index + 1, "open-stream deadline", error))?
        .map_err(|error| sequence_stage_error(index + 1, "open-stream", error))?;
        if !body.is_empty() {
            stream
                .send_data(Bytes::from(body))
                .await
                .map_err(|error| sequence_stage_error(index + 1, "send-body", error))?;
        }
        stream
            .finish()
            .await
            .map_err(|error| sequence_stage_error(index + 1, "finish-upload", error))?;
        streams.push((stream, index + 1));
    }
    let pause_before_read_ms = specification["pause_before_read_ms"]
        .as_u64()
        .ok_or("concurrent request sequence requires pause_before_read_ms")?;
    tokio::time::sleep(std::time::Duration::from_millis(pause_before_read_ms)).await;

    let mut responses = Vec::with_capacity(streams.len());
    for (mut stream, request_index) in streams {
        let response =
            tokio::time::timeout(std::time::Duration::from_secs(10), stream.recv_response())
                .await
                .map_err(|error| {
                    sequence_stage_error(request_index, "receive-headers deadline", error)
                })?
                .map_err(|error| sequence_stage_error(request_index, "receive-headers", error))?;
        let content_type = response
            .headers()
            .get(http::header::CONTENT_TYPE)
            .and_then(|value| value.to_str().ok());
        let mut response_body = Vec::new();
        while let Some(mut data) =
            tokio::time::timeout(std::time::Duration::from_secs(10), stream.recv_data())
                .await
                .map_err(|error| {
                    sequence_stage_error(request_index, "receive-body deadline", error)
                })?
                .map_err(|error| sequence_stage_error(request_index, "receive-body", error))?
        {
            let length = data.remaining();
            response_body.extend_from_slice(data.chunk());
            data.advance(length);
        }
        responses.push(json!({
            "status": response.status().as_u16(),
            "content_type": content_type,
            "body_hex": response_body.iter().map(|byte| format!("{byte:02x}")).collect::<String>(),
            "body_stream_error": false,
            "stream_reset": false
        }));
    }
    hold_sequence_connection(connection, specification, &responses).await?;
    writeln!(
        std::io::stdout().lock(),
        "{}",
        json!({"responses": responses})
    )?;
    endpoint.close(
        quinn::VarInt::from_u32(0x100),
        b"parity concurrent request sequence complete",
    );
    Ok(())
}

async fn wait_for_file(path: &str, purpose: &str) -> Result<(), Box<dyn Error>> {
    let path = std::path::Path::new(path);
    let deadline = tokio::time::Instant::now() + std::time::Duration::from_secs(10);
    while !path.exists() {
        if tokio::time::Instant::now() >= deadline {
            return Err(format!("timed out waiting for {purpose}").into());
        }
        tokio::time::sleep(std::time::Duration::from_millis(10)).await;
    }
    Ok(())
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
    let request_body_chunks = match specification.get("body_chunks_hex") {
        Some(Value::Array(chunks)) => chunks
            .iter()
            .map(|chunk| {
                decode_hex(
                    chunk
                        .as_str()
                        .ok_or("request body chunk must be hexadecimal text")?,
                )
            })
            .collect::<Result<Vec<_>, _>>()?,
        Some(_) => return Err("body_chunks_hex must be an array".into()),
        None if request_body.is_empty() => Vec::new(),
        None => vec![request_body.clone()],
    };
    if request_body_chunks
        .iter()
        .flatten()
        .copied()
        .collect::<Vec<_>>()
        != request_body
    {
        return Err("body_chunks_hex must concatenate to body_hex".into());
    }
    let mut request_trailers = HeaderMap::new();
    if let Some(trailers) = specification.get("trailers").and_then(Value::as_array) {
        for trailer in trailers {
            let pair = trailer.as_array().ok_or("request trailer must be a pair")?;
            if pair.len() != 2 {
                return Err("request trailer must contain exactly two values".into());
            }
            let name = pair[0]
                .as_str()
                .ok_or("request trailer name must be text")?;
            let value = pair[1]
                .as_str()
                .ok_or("request trailer value must be text")?;
            request_trailers.append(
                HeaderName::from_bytes(name.as_bytes())?,
                HeaderValue::from_bytes(value.as_bytes())?,
            );
        }
    }
    let h3_grease = match specification.get("h3_grease") {
        Some(Value::Bool(value)) => *value,
        Some(_) => return Err("h3_grease must be a boolean".into()),
        None => true,
    };
    let abort_after_body = specification["abort_after_body"].as_bool().unwrap_or(false);
    let abort_response_after_headers = specification["abort_response_after_headers"]
        .as_bool()
        .unwrap_or(false);
    let peer_stop_before_response_headers = specification["peer_stop_before_response_headers"]
        .as_bool()
        .unwrap_or(false);
    let same_connection_followup_path = specification["same_connection_followup_path"].as_str();
    let expect_response_error = specification["expect_response_error"]
        .as_bool()
        .unwrap_or(false);
    let leave_upload_open_until_response = specification["leave_upload_open_until_response"]
        .as_bool()
        .unwrap_or(false);
    let empty_data_frame_before_body = specification["empty_data_frame_before_body"]
        .as_bool()
        .unwrap_or(false);
    let malformed_data_frame_after_headers = specification["malformed_data_frame_after_headers"]
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
    let peer_stop_release_file = specification["peer_stop_release_file"].as_str();
    let peer_stop_followup_release_file = specification["peer_stop_followup_release_file"].as_str();
    let hold_result_file = specification["hold_result_file"].as_str();
    let hold_release_file = specification["hold_release_file"].as_str();
    let hold_response_stream_for_shutdown = specification["hold_response_stream_for_shutdown"]
        .as_bool()
        .unwrap_or(false);
    let request_after_first_response_chunk =
        specification.get("request_after_first_response_chunk");
    if request_after_first_response_chunk.is_some()
        && (specification.get("request_sequence").is_some()
            || abort_after_body
            || abort_response_after_headers
            || peer_stop_before_response_headers
            || expect_response_error
            || leave_upload_open_until_response
            || invalid_alpn
            || hold_response_stream_for_shutdown)
    {
        return Err("held response trigger cannot be combined with another client workflow".into());
    }
    if peer_stop_before_response_headers
        && (specification.get("request_sequence").is_some()
            || abort_after_body
            || abort_response_after_headers
            || expect_response_error
            || leave_upload_open_until_response
            || invalid_alpn
            || hold_response_stream_for_shutdown
            || !request_body.is_empty())
    {
        return Err(
            "held-request peer stop cannot be combined with another client workflow".into(),
        );
    }
    if malformed_data_frame_after_headers
        && (specification.get("request_sequence").is_some()
            || abort_after_body
            || abort_response_after_headers
            || peer_stop_before_response_headers
            || expect_response_error
            || leave_upload_open_until_response
            || invalid_alpn
            || hold_response_stream_for_shutdown
            || method != "POST"
            || !request_body.is_empty())
    {
        return Err("truncated DATA probe cannot be combined with another workflow".into());
    }

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
    let sequence_connection = specification
        .get("request_sequence")
        .or(request_after_first_response_chunk)
        .map(|_| connection.clone());
    let raw_connection = connection.clone();
    let client_connection = tokio::time::timeout(
        std::time::Duration::from_secs(2),
        h3::client::builder()
            .send_grease(h3_grease)
            .build(h3_quinn::Connection::new(connection)),
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

    if specification.get("request_sequence").is_some() {
        request_sequence(
            &mut sender,
            &endpoint,
            sequence_connection
                .as_ref()
                .ok_or("missing sequence connection monitor")?,
            address,
            &specification,
        )
        .await?;
        drop(sender);
        tokio::time::timeout(std::time::Duration::from_secs(2), endpoint.wait_idle()).await?;
        return Ok(());
    }

    let authority = specification
        .get("authority")
        .and_then(Value::as_str)
        .map(str::to_owned)
        .unwrap_or_else(|| format!("localhost:{}", address.port()));
    if malformed_data_frame_after_headers {
        let path = specification["path"]
            .as_str()
            .ok_or("missing malformed DATA request path")?;
        let ready_file = specification["malformed_result_file"]
            .as_str()
            .ok_or("malformed DATA workflow is missing its ready file")?;
        let release_file = specification["malformed_release_file"]
            .as_str()
            .ok_or("malformed DATA workflow is missing its release file")?;
        let _malformed_response =
            send_truncated_data_frame(&raw_connection, &authority, path).await?;
        let temporary_ready = std::path::Path::new(ready_file).with_extension("ready.partial");
        std::fs::write(&temporary_ready, b"sent")?;
        std::fs::rename(temporary_ready, ready_file)?;
        wait_for_file(release_file, "the truncated HTTP/3 DATA recovery release").await?;
        let peer_close_code =
            match tokio::time::timeout(std::time::Duration::from_secs(2), raw_connection.closed())
                .await
            {
                Ok(quinn::ConnectionError::ApplicationClosed(close)) => {
                    Some(close.error_code.into_inner())
                }
                Ok(_) | Err(_) => None,
            };
        drop(_malformed_response);
        drop(sender);
        endpoint.close(quinn::VarInt::from_u32(0), b"truncated DATA probe complete");
        tokio::time::timeout(std::time::Duration::from_secs(2), endpoint.wait_idle()).await?;
        writeln!(
            std::io::stdout().lock(),
            "{}",
            json!({
                "malformed_data_frame_sent": true,
                "peer_close_code": peer_close_code
            })
        )?;
        return Ok(());
    }
    let uri: http::Uri = format!("https://{authority}{path}").parse()?;
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
        for chunk in request_body_chunks {
            if let Err(error) = stream.send_data(Bytes::from(chunk)).await {
                if expect_response_error {
                    report_stream_error()?;
                    return Ok(());
                }
                return Err(error.into());
            }
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
        if !request_trailers.is_empty() {
            if let Err(error) = stream.send_trailers(request_trailers).await {
                if expect_response_error {
                    report_stream_error()?;
                    return Ok(());
                }
                return Err(error.into());
            }
        }
        if let Err(error) = stream.finish().await {
            if expect_response_error {
                report_stream_error()?;
                return Ok(());
            }
            return Err(error.into());
        }
    }
    if peer_stop_before_response_headers {
        let release_file = peer_stop_release_file
            .ok_or("HTTP/3 peer-stop workflow is missing its request release file")?;
        let followup_release_file = peer_stop_followup_release_file
            .ok_or("HTTP/3 peer-stop workflow is missing its follow-up release file")?;
        let followup_path = same_connection_followup_path
            .ok_or("HTTP/3 peer-stop workflow is missing its follow-up path")?;
        if !followup_path.starts_with('/') {
            return Err("HTTP/3 peer-stop follow-up path must be origin-form".into());
        }

        wait_for_file(release_file, "the held-request peer-stop release").await?;
        stream.stop_sending(h3::error::Code::H3_REQUEST_CANCELLED);
        wait_for_file(followup_release_file, "the ASGI cancellation observation").await?;
        drop(stream);

        let followup_request = Request::builder()
            .method("GET")
            .uri(format!(
                "https://localhost:{}{followup_path}",
                address.port()
            ))
            .body(())?;
        let mut followup_stream = tokio::time::timeout(
            std::time::Duration::from_secs(2),
            sender.send_request(followup_request),
        )
        .await??;
        followup_stream.finish().await?;
        let followup_response = tokio::time::timeout(
            std::time::Duration::from_secs(2),
            followup_stream.recv_response(),
        )
        .await??;
        let content_type = followup_response
            .headers()
            .get(http::header::CONTENT_TYPE)
            .and_then(|value| value.to_str().ok());
        let ordered_response_headers = followup_response
            .headers()
            .iter()
            .filter(|(name, _)| name.as_str().starts_with("x-asgi-"))
            .map(|(name, value)| {
                json!([
                    name.as_str(),
                    String::from_utf8_lossy(value.as_bytes()).into_owned()
                ])
            })
            .collect::<Vec<_>>();
        let mut followup_body = Vec::new();
        while let Some(mut data) = tokio::time::timeout(
            std::time::Duration::from_secs(2),
            followup_stream.recv_data(),
        )
        .await??
        {
            let length = data.remaining();
            followup_body.extend_from_slice(data.chunk());
            data.advance(length);
        }
        let observation = json!({
            "peer_stop_sent": true,
            "followup": {
                "status": followup_response.status().as_u16(),
                "content_type": content_type,
                "ordered_response_headers": ordered_response_headers,
                "body_hex": followup_body.iter().map(|byte| format!("{byte:02x}")).collect::<String>(),
                "body_stream_error": false
            }
        });
        drop(followup_stream);
        drop(sender);
        endpoint.close(quinn::VarInt::from_u32(0), b"parity peer stop observed");
        tokio::time::timeout(std::time::Duration::from_secs(2), endpoint.wait_idle()).await?;
        writeln!(std::io::stdout().lock(), "{observation}")?;
        return Ok(());
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
    if let Some(trigger) = request_after_first_response_chunk {
        let connection = sequence_connection
            .as_ref()
            .ok_or("held response trigger is missing its connection monitor")?;
        let (Some(result_file), Some(release_file)) = (hold_result_file, hold_release_file) else {
            return Err("held response trigger is missing synchronization files".into());
        };
        let trigger = trigger
            .as_object()
            .ok_or("request_after_first_response_chunk must be a request object")?;
        if trigger.len() != 4
            || !["method", "path", "headers", "body_hex"]
                .iter()
                .all(|field| trigger.contains_key(*field))
        {
            return Err(
                "held response trigger must contain only method, path, headers, and body_hex"
                    .into(),
            );
        }
        let trigger_method = trigger["method"].as_str().ok_or("missing trigger method")?;
        let trigger_path = trigger["path"].as_str().ok_or("missing trigger path")?;
        if !trigger_path.starts_with('/') {
            return Err("held response trigger path must be origin-form".into());
        }
        let trigger_body = decode_hex(trigger["body_hex"].as_str().ok_or("missing trigger body")?)?;
        let mut trigger_builder = Request::builder().method(trigger_method).uri(format!(
            "https://localhost:{}{}",
            address.port(),
            trigger_path
        ));
        let trigger_headers = trigger["headers"]
            .as_array()
            .ok_or("trigger headers must be an array")?;
        for header in trigger_headers {
            let pair = header.as_array().ok_or("trigger header must be a pair")?;
            if pair.len() != 2 {
                return Err("trigger header must contain exactly two values".into());
            }
            let name = pair[0].as_str().ok_or("trigger header name must be text")?;
            let value = pair[1]
                .as_str()
                .ok_or("trigger header value must be text")?;
            trigger_builder =
                trigger_builder.header(HeaderName::from_bytes(name.as_bytes())?, value);
        }
        if !trigger_body.is_empty()
            && !trigger_headers.iter().any(|header| {
                header[0]
                    .as_str()
                    .is_some_and(|name| name.eq_ignore_ascii_case("content-length"))
            })
        {
            trigger_builder =
                trigger_builder.header(http::header::CONTENT_LENGTH, trigger_body.len());
        }
        let trigger_request = trigger_builder.body(())?;
        if status != 200 {
            return Err(
                format!("held response returned status {status} before its trigger").into(),
            );
        }
        let Some(mut first_data) =
            tokio::time::timeout(std::time::Duration::from_secs(2), stream.recv_data()).await??
        else {
            return Err("held response completed before its first body chunk".into());
        };
        if !first_data.has_remaining() {
            return Err("held response did not provide a nonempty first body chunk".into());
        }
        let length = first_data.remaining();
        body.extend_from_slice(first_data.chunk());
        first_data.advance(length);
        let first_chunk_observation = json!({
            "status": status,
            "content_type": content_type,
            "body_hex": body.iter().map(|byte| format!("{byte:02x}")).collect::<String>(),
            "body_stream_error": false,
            "stream_reset": false,
            "connection_closed": false,
            "first_body_chunk_received": true
        });
        let temporary_result =
            std::path::Path::new(result_file).with_extension("http3-held-response.partial");
        std::fs::write(
            &temporary_result,
            serde_json::to_vec(&first_chunk_observation)?,
        )?;
        std::fs::rename(temporary_result, result_file)?;
        let deadline = tokio::time::Instant::now() + std::time::Duration::from_secs(15);
        while !std::path::Path::new(release_file).exists() {
            if let Some(error) = connection.close_reason() {
                return Err(
                    format!("HTTP/3 peer closed before held response release: {error}").into(),
                );
            }
            if tokio::time::Instant::now() >= deadline {
                return Err("timed out waiting for HTTP/3 held response release".into());
            }
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        }
        if let Some(error) = connection.close_reason() {
            return Err(format!("HTTP/3 peer closed before held response trigger: {error}").into());
        }
        // Retain both streams until peer failure so local stream destruction
        // cannot manufacture the cancellation observed by the runner.
        let mut trigger_stream = tokio::time::timeout(
            std::time::Duration::from_secs(2),
            sender.send_request(trigger_request),
        )
        .await??;
        let mut trigger_error = None;
        if !trigger_body.is_empty() {
            if let Err(error) = tokio::time::timeout(
                std::time::Duration::from_secs(2),
                trigger_stream.send_data(Bytes::from(trigger_body)),
            )
            .await?
            {
                trigger_error = Some(error.to_string());
            }
        }
        if trigger_error.is_none() {
            if let Err(error) =
                tokio::time::timeout(std::time::Duration::from_secs(2), trigger_stream.finish())
                    .await?
            {
                trigger_error = Some(error.to_string());
            }
        }
        let peer_error =
            tokio::time::timeout(std::time::Duration::from_secs(2), connection.closed()).await?;
        let peer_close_code = match peer_error {
            quinn::ConnectionError::ApplicationClosed(close) => close.error_code.into_inner(),
            error => {
                return Err(
                    format!("held response requires a remote application close: {error}").into(),
                )
            }
        };
        let response_incomplete = loop {
            match tokio::time::timeout(std::time::Duration::from_secs(2), stream.recv_data())
                .await?
            {
                Err(_) => break true,
                Ok(None) => break false,
                Ok(Some(mut data)) => {
                    let length = data.remaining();
                    body.extend_from_slice(data.chunk());
                    data.advance(length);
                }
            }
        };
        let observation = json!({
            "status": status,
            "content_type": content_type,
            "body_hex": body.iter().map(|byte| format!("{byte:02x}")).collect::<String>(),
            "body_stream_error": response_incomplete,
            "stream_reset": response_incomplete,
            "connection_closed": true,
            "first_body_chunk_received": true,
            "response_incomplete": response_incomplete,
            "peer_close_code": peer_close_code,
            "trigger_request_sent": true,
            "trigger_error": trigger_error
        });
        drop(trigger_stream);
        drop(stream);
        drop(sender);
        tokio::time::timeout(std::time::Duration::from_secs(2), endpoint.wait_idle()).await?;
        writeln!(std::io::stdout().lock(), "{}", observation)?;
        return Ok(());
    }
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
    let ordered_response_headers = response
        .headers()
        .iter()
        .filter(|(name, _)| name.as_str().starts_with("x-asgi-"))
        .map(|(name, value)| {
            json!([
                name.as_str(),
                String::from_utf8_lossy(value.as_bytes()).into_owned()
            ])
        })
        .collect::<Vec<_>>();
    let observation = json!({
        "status": status,
        "content_type": content_type,
        "ordered_response_headers": ordered_response_headers,
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
