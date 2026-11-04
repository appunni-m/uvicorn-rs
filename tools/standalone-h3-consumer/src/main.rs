use std::{
    error::Error,
    fs::File,
    future::Future,
    io::{self, BufReader, ErrorKind},
    pin::Pin,
    task::{Context, Poll},
};

use bytes::Bytes;
use http::{Request, Response, StatusCode};
use http_body_util::{BodyExt, Full};
use rustls::{ServerConfig, pki_types::CertificateDer};
use tower_service::Service;
use uvicorn_rs::{
    Http3Endpoint, Http3RequestBody, Http3ServerConfig, ServerConfig as UvicornConfig,
    serve_http3,
};

type ResponseFuture =
    Pin<Box<dyn Future<Output = Result<Response<Full<Bytes>>, io::Error>> + Send>>;

#[derive(Clone)]
struct ConsumerApp;

impl Service<Request<Http3RequestBody>> for ConsumerApp {
    type Response = Response<Full<Bytes>>;
    type Error = io::Error;
    type Future = ResponseFuture;

    fn poll_ready(&mut self, _context: &mut Context<'_>) -> Poll<Result<(), Self::Error>> {
        Poll::Ready(Ok(()))
    }

    fn call(&mut self, request: Request<Http3RequestBody>) -> Self::Future {
        Box::pin(async move {
            let status = if request.uri().path() == "/state" {
                StatusCode::OK
            } else {
                StatusCode::NO_CONTENT
            };
            // Drive the archived crate's request-body path. A clean FIN before
            // the declared DATA payload ends must surface as H3_FRAME_ERROR.
            let _body_result = request.into_body().collect().await;
            let mut response = Response::new(Full::new(Bytes::from_static(b"healthy")));
            *response.status_mut() = status;
            Ok(response)
        })
    }
}

fn read_certificates(path: &str) -> Result<Vec<CertificateDer<'static>>, Box<dyn Error>> {
    let file = File::open(path)?;
    let certificates =
        rustls_pemfile::certs(&mut BufReader::new(file)).collect::<Result<Vec<_>, _>>()?;
    if certificates.is_empty() {
        return Err(io::Error::new(ErrorKind::InvalidData, "certificate file is empty").into());
    }
    Ok(certificates)
}

fn server_config(
    certificate_path: &str,
    key_path: &str,
) -> Result<Http3ServerConfig, Box<dyn Error>> {
    let certificates = read_certificates(certificate_path)?;
    let key_file = File::open(key_path)?;
    let key = rustls_pemfile::private_key(&mut BufReader::new(key_file))?
        .ok_or_else(|| io::Error::new(ErrorKind::InvalidData, "private key file is empty"))?;
    let tls = ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(certificates, key)?;
    Ok(Http3ServerConfig::from_rustls_config(tls)?)
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args().skip(1);
    let certificate_path = args.next().ok_or_else(|| {
        io::Error::new(ErrorKind::InvalidInput, "missing server certificate path")
    })?;
    let key_path = args
        .next()
        .ok_or_else(|| io::Error::new(ErrorKind::InvalidInput, "missing server key path"))?;

    let endpoint = Http3Endpoint::bind(
        "127.0.0.1:0".parse()?,
        server_config(&certificate_path, &key_path)?,
    )?;
    let address = endpoint.local_addr()?;
    println!("READY {address}");

    let shutdown = async {
        let _ = tokio::signal::ctrl_c().await;
    };
    let server = serve_http3(endpoint, ConsumerApp, shutdown, UvicornConfig::default());
    server.await?;
    Ok(())
}
