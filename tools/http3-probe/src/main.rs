use std::error::Error;
use std::net::SocketAddr;
use std::sync::Arc;

use bytes::Buf;
use h3_quinn::quinn::{self, rustls};
use http::Request;

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args().skip(1);
    let address: SocketAddr = args.next().ok_or("missing server address")?.parse()?;
    let certfile = args.next().ok_or("missing CA certificate")?;

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
    let connection = endpoint.connect(address, "localhost")?.await?;
    let (mut driver, mut sender) = h3::client::new(h3_quinn::Connection::new(connection)).await?;
    tokio::spawn(async move {
        let _ = std::future::poll_fn(|cx| driver.poll_close(cx)).await;
    });

    let uri: http::Uri = format!("https://localhost:{}/protocol", address.port()).parse()?;
    let request = Request::builder().uri(uri).body(())?;
    let mut stream = sender.send_request(request).await?;
    stream.finish().await?;
    let response = stream.recv_response().await?;
    if !response.status().is_success() {
        return Err(format!("unexpected HTTP/3 response status: {}", response.status()).into());
    }
    let mut body = Vec::new();
    while let Some(mut data) = stream.recv_data().await? {
        let len = data.remaining();
        body.extend_from_slice(data.chunk());
        data.advance(len);
    }
    let body = String::from_utf8(body)?;
    if body != "http_version=3" {
        return Err(format!("HTTP/3 ASGI scope mismatch: {body:?}").into());
    }
    println!("PASS: HTTP/3 request scope reports {body}");
    endpoint.close(quinn::VarInt::from_u32(0), b"probe complete");
    endpoint.wait_idle().await;
    Ok(())
}
