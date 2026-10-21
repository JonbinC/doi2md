fn main() {
    println!(
        "cargo:rustc-env=MDTERO_NATIVE_TARGET={}",
        std::env::var("TARGET").expect("Cargo target")
    );
    tauri_build::build()
}
