#![allow(
    clippy::print_stdout,
    reason = "Cargo build scripts emit compiler configuration directives on stdout"
)]

fn main() {
    println!("cargo:rustc-check-cfg=cfg(uvicorn_rs_native_transport)");
    println!("cargo:rustc-cfg=uvicorn_rs_native_transport");
}
