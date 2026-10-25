//! Coverage-only contracts for Rust paths that cannot be reached through
//! valid network input.

use std::{
    error::Error,
    future::Future,
    io,
    pin::Pin,
    sync::atomic::{AtomicU8, Ordering},
    time::Duration,
};

use tokio::io::{AsyncRead, AsyncWrite};
use tokio::sync::watch;

use super::{ConnectionError, wait_for_connection_or_response_after_peer_read_error};

static HTTP1_UNIX_PEER_READ_ON_READ_ERROR_FAULT: AtomicU8 = AtomicU8::new(0);

/// Arms a coverage-only Unix OnRead error for the peer-read adapter contract.
#[doc(hidden)]
pub fn arm_http1_unix_peer_read_on_read_error_fault() -> bool {
    HTTP1_UNIX_PEER_READ_ON_READ_ERROR_FAULT
        .compare_exchange(0, 1, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

/// Finishes the coverage-only Unix OnRead peer-read error contract.
#[doc(hidden)]
pub fn finish_http1_unix_peer_read_on_read_error_fault() -> bool {
    HTTP1_UNIX_PEER_READ_ON_READ_ERROR_FAULT.swap(0, Ordering::AcqRel) == 3
}

pub(super) fn take_http1_unix_peer_read_on_read_error_fault() -> bool {
    HTTP1_UNIX_PEER_READ_ON_READ_ERROR_FAULT
        .compare_exchange(1, 2, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
}

pub(super) fn observe_http1_unix_peer_read_on_read_error_fault() {
    let _ = HTTP1_UNIX_PEER_READ_ON_READ_ERROR_FAULT.compare_exchange(
        2,
        3,
        Ordering::AcqRel,
        Ordering::Acquire,
    );
}

/// Checks the source-chain contract for each private HTTP connection error.
pub fn connection_error_source_variants() -> Result<(), Box<dyn Error + Send + Sync + 'static>> {
    let http_source = io::Error::other("HTTP connection source");
    let http_error = ConnectionError::Http(Box::new(http_source));
    verify_io_error_source(&http_error, "HTTP connection source")?;

    let upgrade_source = io::Error::other("upgraded session source");
    let upgrade_error = ConnectionError::Upgrade(Box::new(upgrade_source));
    verify_io_error_source(&upgrade_error, "upgraded session source")?;

    let tls_error = ConnectionError::Tls(io::Error::other("TLS connection source"));
    verify_io_error_source(&tls_error, "TLS connection source")?;

    let peer_read_error = ConnectionError::PeerRead(io::ErrorKind::ConnectionReset);
    if Error::source(&peer_read_error).is_some() {
        return Err(io::Error::other("peer-read errors must not expose a source").into());
    }

    Ok(())
}

fn verify_io_error_source(
    error: &ConnectionError,
    expected_message: &str,
) -> Result<(), Box<dyn Error + Send + Sync + 'static>> {
    let source = Error::source(error)
        .ok_or_else(|| io::Error::other("connection error omitted its I/O source"))?;
    if !source.is::<io::Error>() || source.to_string() != expected_message {
        return Err(io::Error::other("connection error returned the wrong source").into());
    }
    Ok(())
}

/// Builds an OnRead peer adapter for the native adapter contract.
pub fn http1_on_read_peer_read(
    stream: tokio::net::TcpStream,
) -> super::CoveragePeerReadAdapter<impl AsyncRead + AsyncWrite + Unpin + Send> {
    let (io, observer, failed_observer, pump, _) =
        super::peer_read::observe_peer_read(stream, super::PeerReadHalfCloseMode::OnRead);
    let pump = pump.map(|pump| {
        Box::pin(async move {
            let _ = pump.await;
        }) as Pin<Box<dyn Future<Output = ()> + Send>>
    });
    super::CoveragePeerReadAdapter {
        io,
        observer,
        failed_observer,
        pump,
    }
}

/// Builds an OnRead Unix-domain socket peer adapter for the native adapter
/// contract. This entry point is absent from normal builds.
#[cfg(unix)]
pub fn http1_on_read_unix_peer_read(
    stream: tokio::net::UnixStream,
) -> super::CoveragePeerReadAdapter<impl AsyncRead + AsyncWrite + Unpin + Send> {
    let (io, observer, failed_observer, pump, _) =
        super::peer_read::observe_peer_read_unix(stream, super::PeerReadHalfCloseMode::OnRead);
    let pump = pump.map(|pump| {
        Box::pin(async move {
            let _ = pump.await;
        }) as Pin<Box<dyn Future<Output = ()> + Send>>
    });
    super::CoveragePeerReadAdapter {
        io,
        observer,
        failed_observer,
        pump,
    }
}

/// Builds a Proactive Unix-domain socket peer adapter for the native adapter
/// contract. This entry point is absent from normal builds.
#[cfg(unix)]
pub fn http1_proactive_unix_peer_read(
    stream: tokio::net::UnixStream,
) -> super::CoveragePeerReadAdapter<impl AsyncRead + AsyncWrite + Unpin + Send> {
    let (io, observer, failed_observer, pump, _) =
        super::peer_read::observe_peer_read_unix(stream, super::PeerReadHalfCloseMode::Proactive);
    let pump = pump.map(|pump| {
        Box::pin(async move {
            let _ = pump.await;
        }) as Pin<Box<dyn Future<Output = ()> + Send>>
    });
    super::CoveragePeerReadAdapter {
        io,
        observer,
        failed_observer,
        pump,
    }
}

/// Exercises active-response, inactive-change, and closed-channel outcomes
/// for the HTTP/1 peer-read supervisor's response-body activity watch.
pub async fn http1_response_activity_watch_outcomes()
-> Result<(), Box<dyn Error + Send + Sync + 'static>> {
    let (closed_sender, mut closed_receiver) = watch::channel(0usize);
    drop(closed_sender);

    let closed_connection = async {
        tokio::time::sleep(Duration::from_millis(1)).await;
        Ok::<(), ConnectionError>(())
    };
    tokio::pin!(closed_connection);
    wait_for_connection_or_response_after_peer_read_error(
        closed_connection.as_mut(),
        &mut closed_receiver,
        io::ErrorKind::ConnectionReset,
    )
    .await?;

    let (inactive_sender, mut inactive_receiver) = watch::channel(0usize);
    let sender_task = tokio::spawn(async move {
        tokio::task::yield_now().await;
        inactive_sender.send_replace(0);
    });
    let inactive_connection = async {
        tokio::time::sleep(Duration::from_millis(25)).await;
        Ok::<(), ConnectionError>(())
    };
    tokio::pin!(inactive_connection);
    wait_for_connection_or_response_after_peer_read_error(
        inactive_connection.as_mut(),
        &mut inactive_receiver,
        io::ErrorKind::ConnectionReset,
    )
    .await?;
    sender_task.await?;

    let (_active_sender, mut active_receiver) = watch::channel(1usize);
    let active_connection = async {
        tokio::time::sleep(Duration::from_millis(25)).await;
        Ok::<(), ConnectionError>(())
    };
    tokio::pin!(active_connection);
    let active_result = wait_for_connection_or_response_after_peer_read_error(
        active_connection.as_mut(),
        &mut active_receiver,
        io::ErrorKind::ConnectionReset,
    )
    .await;
    if !matches!(
        active_result,
        Err(ConnectionError::PeerRead(io::ErrorKind::ConnectionReset))
    ) {
        return Err(io::Error::other(
            "active response activity did not preserve the peer-read error",
        )
        .into());
    }

    Ok(())
}
