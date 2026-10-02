use std::error::Error;
use std::io::BufReader;
use std::net::SocketAddr;
use std::sync::Arc;

use bytes::Buf;
use h3_quinn::quinn::{self, rustls};
use http::Request;
use serde_json::json;

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args().skip(1);
    let address: SocketAddr = args.next().ok_or("missing server address")?.parse()?;
    let certfile = args.next().ok_or("missing trusted certificate")?;
    let path = args.next().ok_or("missing request path")?;

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
    tls.alpn_protocols = vec![b"h3".to_vec()];

    let mut endpoint = quinn::Endpoint::client("0.0.0.0:0".parse()?)?;
    let quic_tls = quinn::crypto::rustls::QuicClientConfig::try_from(tls)?;
    endpoint.set_default_client_config(quinn::ClientConfig::new(Arc::new(quic_tls)));
    let connection = endpoint.connect(address, "localhost")?.await?;
    let (mut driver, mut sender) = h3::client::new(h3_quinn::Connection::new(connection)).await?;
    tokio::spawn(async move {
        let _ = std::future::poll_fn(|cx| driver.poll_close(cx)).await;
    });

    let uri: http::Uri = format!("https://localhost:{}{}", address.port(), path).parse()?;
    let request = Request::builder().uri(uri).body(())?;
    let mut stream = sender.send_request(request).await?;
    stream.finish().await?;
    let response = stream.recv_response().await?;
    let status = response.status().as_u16();
    let content_type = response
        .headers()
        .get(http::header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok());
    let mut body = Vec::new();
    while let Some(mut data) = stream.recv_data().await? {
        let length = data.remaining();
        body.extend_from_slice(data.chunk());
        data.advance(length);
    }
    let body_hex = body
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    println!(
        "{}",
        json!({"status": status, "content_type": content_type, "body_hex": body_hex})
    );
    endpoint.close(quinn::VarInt::from_u32(0), b"parity request complete");
    endpoint.wait_idle().await;
    Ok(())
}
