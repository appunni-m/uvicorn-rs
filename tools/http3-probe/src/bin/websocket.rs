use std::error::Error;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use bytes::Bytes;
use futures_util::{future::join_all, SinkExt, StreamExt};
use tokio::time::timeout;
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use tokio_tungstenite::tungstenite::http::header::SEC_WEBSOCKET_PROTOCOL;
use tokio_tungstenite::tungstenite::Message;

type BenchError = Box<dyn Error + Send + Sync>;

fn percentile(values: &[f64], p: f64) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let index = ((p * values.len() as f64).ceil() as usize).saturating_sub(1);
    values[index.min(values.len() - 1)]
}

fn check_subprotocol<B>(response: &tokio_tungstenite::tungstenite::http::Response<B>) -> Result<(), String> {
    match response.headers().get(SEC_WEBSOCKET_PROTOCOL) {
        Some(value) if value == "bench" => Ok(()),
        actual => Err(format!("unexpected WebSocket subprotocol: {actual:?}")),
    }
}

#[tokio::main]
async fn main() -> Result<(), BenchError> {
    let mut args = std::env::args().skip(1);
    let address = args.next().ok_or("missing WebSocket address")?;
    let seconds: f64 = args.next().ok_or("missing duration")?.parse()?;
    let concurrency: usize = args.next().ok_or("missing concurrency")?.parse()?;
    let mode = args.next().ok_or("missing mode")?;
    let path = args.next().ok_or("missing path")?;
    let payload_bytes: usize = args.next().ok_or("missing payload size")?.parse()?;
    let max_requests: usize = args.next().unwrap_or_else(|| "0".to_string()).parse()?;
    if concurrency == 0 || seconds <= 0.0 {
        return Err("concurrency and duration must be positive".into());
    }

    let uri = format!("ws://{address}{path}");
    let payload = Arc::new(Bytes::from(vec![b'x'; payload_bytes]));
    let text_payload = Arc::new("x".repeat(payload_bytes));

    if mode == "handshake" {
        let started = Instant::now();
        let deadline = started + Duration::from_secs_f64(seconds);
        let next_request = Arc::new(AtomicUsize::new(0));
        let workers = (0..concurrency).map(|_| {
            let uri = uri.clone();
            let next_request = Arc::clone(&next_request);
            async move {
                let mut latencies = Vec::new();
                let mut failure = None;
                while Instant::now() < deadline {
                    if max_requests > 0
                        && next_request.fetch_add(1, Ordering::Relaxed) >= max_requests
                    {
                        break;
                    }
                    let request_started = Instant::now();
                    let mut request = match uri.as_str().into_client_request() {
                        Ok(request) => request,
                        Err(error) => {
                            failure = Some(error.to_string());
                            break;
                        }
                    };
                    request.headers_mut().insert(SEC_WEBSOCKET_PROTOCOL, "bench".parse().unwrap());
                    let (mut socket, response) = match timeout(
                        Duration::from_secs(5),
                        tokio_tungstenite::connect_async(request),
                    )
                    .await
                    {
                        Ok(Ok(connection)) => connection,
                        Ok(Err(error)) => {
                            failure = Some(format!("WebSocket handshake failed: {error}"));
                            break;
                        }
                        Err(_) => {
                            failure = Some("WebSocket handshake timed out".to_string());
                            break;
                        }
                    };
                    if let Err(error) = check_subprotocol(&response) {
                        failure = Some(error);
                        break;
                    }
                    if let Err(error) = timeout(Duration::from_secs(5), socket.close(None)).await {
                        failure = Some(format!("WebSocket close timed out: {error}"));
                        break;
                    }
                    latencies.push(request_started.elapsed().as_secs_f64() * 1000.0);
                }
                (latencies, failure)
            }
        });
        let results = join_all(workers).await;
        let elapsed = started.elapsed().as_secs_f64();
        let mut latencies = Vec::new();
        let mut failures = Vec::new();
        for (samples, failure) in results {
            latencies.extend(samples);
            if let Some(failure) = failure {
                failures.push(failure);
            }
        }
        return report(latencies, elapsed, 0, 0, failures);
    }

    let connections = (0..concurrency).map(|_| {
        let uri = uri.clone();
        async move {
            let mut request = uri.as_str().into_client_request()?;
            request.headers_mut().insert(SEC_WEBSOCKET_PROTOCOL, "bench".parse().unwrap());
            let (socket, response) = timeout(
                Duration::from_secs(5),
                tokio_tungstenite::connect_async(request),
            )
            .await??;
            check_subprotocol(&response).map_err(std::io::Error::other)?;
            Ok::<_, Box<dyn Error + Send + Sync>>(socket)
        }
    });
    let mut sockets = join_all(connections)
        .await
        .into_iter()
        .collect::<Result<Vec<_>, _>>()?;

    for socket in &mut sockets {
        let message = if mode == "text" {
            Message::Text(text_payload.as_str().into())
        } else {
            Message::Binary(payload.as_ref().clone())
        };
        socket.send(message.clone()).await?;
        let echoed = timeout(Duration::from_secs(5), socket.next())
            .await
            .map_err(std::io::Error::other)?
            .ok_or_else(|| std::io::Error::other("WebSocket closed before warm-up echo"))??;
        let matches = match (&message, &echoed) {
            (Message::Text(wanted), Message::Text(actual)) => wanted == actual,
            (Message::Binary(wanted), Message::Binary(actual)) => wanted == actual,
            _ => false,
        };
        if !matches {
            return Err("WebSocket warm-up echo did not match the complete payload".into());
        }
    }

    let started = Instant::now();
    let deadline = started + Duration::from_secs_f64(seconds);
    let is_text = mode == "text";
    let workers = sockets.into_iter().map(|mut socket| {
        let payload = Arc::clone(&payload);
        let text_payload = Arc::clone(&text_payload);
        let is_text = is_text;
        async move {
            let mut latencies = Vec::new();
            let mut request_bytes = 0_u64;
            let mut response_bytes = 0_u64;
            let mut failure = None;
            while Instant::now() < deadline {
                let message = if is_text {
                    Message::Text(text_payload.as_str().into())
                } else {
                    Message::Binary(payload.as_ref().clone())
                };
                let request_started = Instant::now();
                if let Err(error) = socket.send(message.clone()).await {
                    failure = Some(format!("WebSocket send failed: {error}"));
                    break;
                }
                let echoed = match timeout(Duration::from_secs(5), socket.next()).await {
                    Ok(Some(Ok(message))) => message,
                    Ok(Some(Err(error))) => {
                        failure = Some(format!("WebSocket receive failed: {error}"));
                        break;
                    }
                    Ok(None) => {
                        failure = Some("WebSocket closed before echo".to_string());
                        break;
                    }
                    Err(_) => {
                        failure = Some("WebSocket echo timed out".to_string());
                        break;
                    }
                };
                let matches = match (&message, &echoed) {
                    (Message::Text(wanted), Message::Text(actual)) => wanted == actual,
                    (Message::Binary(wanted), Message::Binary(actual)) => wanted == actual,
                    _ => false,
                };
                if !matches {
                    failure = Some("WebSocket echo did not match the complete payload".to_string());
                    break;
                }
                let size = if is_text { text_payload.len() } else { payload.len() };
                request_bytes += size as u64;
                response_bytes += size as u64;
                latencies.push(request_started.elapsed().as_secs_f64() * 1000.0);
            }
            let _ = timeout(Duration::from_secs(1), socket.close(None)).await;
            (latencies, request_bytes, response_bytes, failure)
        }
    });
    let results = join_all(workers).await;
    let elapsed = started.elapsed().as_secs_f64();
    let mut latencies = Vec::new();
    let mut request_bytes = 0_u64;
    let mut response_bytes = 0_u64;
    let mut failures = Vec::new();
    for (samples, sent, received, failure) in results {
        latencies.extend(samples);
        request_bytes += sent;
        response_bytes += received;
        if let Some(failure) = failure {
            failures.push(failure);
        }
    }
    report(latencies, elapsed, request_bytes, response_bytes, failures)
}

fn report(
    mut latencies: Vec<f64>,
    elapsed: f64,
    request_bytes: u64,
    response_bytes: u64,
    failures: Vec<String>,
) -> Result<(), BenchError> {
    latencies.sort_by(f64::total_cmp);
    let requests = latencies.len();
    let first_failure = failures.first().map(|failure| serde_json::json!(failure));
    println!(
        "{{\"requests\":{requests},\"duration_seconds\":{elapsed:.9},\"messages_per_second\":{:.3},\"request_body_bytes\":{request_bytes},\"response_body_bytes\":{response_bytes},\"payload_bytes_per_second\":{:.3},\"p50_ms\":{:.6},\"p95_ms\":{:.6},\"p99_ms\":{:.6},\"failures\":{},\"first_failure\":{}}}",
        requests as f64 / elapsed,
        (request_bytes + response_bytes) as f64 / elapsed,
        percentile(&latencies, 0.50),
        percentile(&latencies, 0.95),
        percentile(&latencies, 0.99),
        failures.len(),
        first_failure.map(|value| value.to_string()).unwrap_or_else(|| "null".to_string()),
    );
    if !failures.is_empty() || requests == 0 {
        return Err("WebSocket benchmark correctness gate failed".into());
    }
    Ok(())
}
