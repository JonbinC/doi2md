use serde::Deserialize;
use std::path::Path;
use url::{Host, Url};

#[derive(Deserialize)]
pub struct Handshake {
    pub protocol: u32,
    pub status: String,
    pub product: String,
    pub host: String,
    pub port: u16,
    pub url: String,
}

pub fn parse_handshake(line: &str) -> Result<Url, &'static str> {
    let data: Handshake = serde_json::from_str(line).map_err(|_| "invalid_bridge_handshake")?;
    let url = Url::parse(&data.url).map_err(|_| "invalid_bridge_url")?;
    if data.protocol != 1
        || data.status != "running"
        || data.product != "mdtero-connect"
        || data.host != "127.0.0.1"
        || data.port == 0
        || url.scheme() != "http"
        || url.host() != Some(Host::Ipv4(std::net::Ipv4Addr::LOCALHOST))
        || url.port_or_known_default() != Some(data.port)
        || !url.username().is_empty()
        || url.password().is_some()
        || url.path() != "/"
        || url.query().is_some()
        || url.fragment().is_some()
    {
        return Err("invalid_bridge_url");
    }
    Ok(url)
}

pub fn same_bridge(url: &Url, origin: &Url) -> bool {
    url.origin() == origin.origin() && url.username().is_empty() && url.password().is_none()
}

pub fn allow_navigation(url: &Url, origin: Option<&Url>) -> bool {
    if let Some(origin) = origin {
        if same_bridge(url, origin) {
            return true;
        }
        if url.scheme() == "blob" {
            return Url::parse(url.path()).is_ok_and(|inner| same_bridge(&inner, origin));
        }
        return false;
    }
    matches!(url.scheme(), "tauri" | "http" | "https") && url.host_str() == Some("tauri.localhost")
        || url.scheme() == "tauri" && url.host_str() == Some("localhost")
}

pub fn safe_filename(path: &Path) -> String {
    let raw = path
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or("mdtero-export.bin");
    let clean: String = raw
        .chars()
        .take(160)
        .map(|c| {
            if c.is_ascii_alphanumeric() || matches!(c, '.' | '-' | '_' | ' ') {
                c
            } else {
                '_'
            }
        })
        .collect();
    let clean = clean.trim_matches(['.', ' ']);
    if clean.is_empty() {
        "mdtero-export.bin".into()
    } else {
        clean.into()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn origin() -> Url {
        Url::parse("http://127.0.0.1:18741/").unwrap()
    }
    #[test]
    fn validates_real_loopback_handshake() {
        assert_eq!(parse_handshake(r#"{"protocol":1,"status":"running","product":"mdtero-connect","host":"127.0.0.1","port":18741,"url":"http://127.0.0.1:18741/"}"#).unwrap(), origin());
    }
    #[test]
    fn rejects_remote_or_credential_urls() {
        for host in ["example.com", "127.0.0.1.evil.test", "user@127.0.0.1"] {
            let s = format!(
                r#"{{"protocol":1,"status":"running","product":"mdtero-connect","host":"127.0.0.1","port":18741,"url":"http://{host}:18741/"}}"#
            );
            assert!(parse_handshake(&s).is_err());
        }
    }
    #[test]
    fn remote_pages_have_no_navigation_path_into_the_webview() {
        for value in [
            "https://example.com",
            "http://127.0.0.1:18742/",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "blob:https://example.com/id",
            "tauri://localhost/",
            "http://tauri.localhost/",
        ] {
            assert!(!allow_navigation(
                &Url::parse(value).unwrap(),
                Some(&origin())
            ));
        }
        assert!(allow_navigation(
            &Url::parse("blob:http://127.0.0.1:18741/id").unwrap(),
            Some(&origin())
        ));
        assert!(allow_navigation(&origin(), Some(&origin())));
    }
    #[test]
    fn export_names_cannot_escape_the_download_folder() {
        assert_eq!(safe_filename(Path::new("/tmp/../../refs.bib")), "refs.bib");
        assert!(!safe_filename(Path::new("..\\..\\x:bad.zip")).contains('\\'));
        assert_eq!(safe_filename(Path::new("...")), "mdtero-export.bin");
    }
}
