package domains

import (
	"net"
	"net/url"
	"strings"
)

var localHosts = map[string]struct{}{
	"localhost":             {},
	"localhost.localdomain": {},
	"127.0.0.1":             {},
	"::1":                   {},
}

func Allowed(rawURL string) bool {
	return RejectionReason(rawURL) == ""
}

func RejectionReason(rawURL string) string {
	parsed, err := url.Parse(strings.TrimSpace(rawURL))
	if err != nil {
		return "relay_url_invalid"
	}
	scheme := strings.ToLower(strings.TrimSpace(parsed.Scheme))
	if scheme != "http" && scheme != "https" {
		return "relay_url_scheme_unsupported"
	}
	host := strings.ToLower(strings.TrimSuffix(strings.TrimSpace(parsed.Hostname()), "."))
	if host == "" {
		return "relay_url_host_missing"
	}
	if _, ok := localHosts[host]; ok || strings.HasSuffix(host, ".localhost") {
		return "relay_url_private_host_blocked"
	}
	if hostResolvesPrivate(host) {
		return "relay_url_private_host_blocked"
	}
	for _, suffix := range allowedSuffixes {
		if host == suffix || strings.HasSuffix(host, "."+suffix) {
			return ""
		}
	}
	return "relay_url_domain_not_allowed"
}

func hostResolvesPrivate(host string) bool {
	if ip := net.ParseIP(host); ip != nil {
		return ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() || ip.IsUnspecified()
	}
	ips, err := net.LookupIP(host)
	if err != nil || len(ips) == 0 {
		return false
	}
	for _, ip := range ips {
		if ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() || ip.IsLinkLocalMulticast() || ip.IsUnspecified() {
			return true
		}
	}
	return false
}
