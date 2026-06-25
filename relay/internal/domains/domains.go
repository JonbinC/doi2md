package domains

import (
	"net"
	"net/url"
	"strings"
)

var allowedSuffixes = []string{
	"academic.oup.com",
	"acm.org",
	"api.crossref.org",
	"api.elsevier.com",
	"api.openalex.org",
	"arxiv.org",
	"cambridge.org",
	"cell.com",
	"crossref.org",
	"dl.acm.org",
	"doi.org",
	"elsevier.com",
	"frontiersin.org",
	"ieeexplore.ieee.org",
	"ieee.org",
	"journals.aps.org",
	"link.springer.com",
	"mdpi.com",
	"nature.com",
	"ncbi.nlm.nih.gov",
	"onlinelibrary.wiley.com",
	"openalex.org",
	"oup.com",
	"plos.org",
	"pnas.org",
	"pubmed.ncbi.nlm.nih.gov",
	"sagepub.com",
	"science.org",
	"sciencedirect.com",
	"springer.com",
	"tandfonline.com",
	"wiley.com",
}

var localHosts = map[string]struct{}{
	"localhost":              {},
	"localhost.localdomain":  {},
	"127.0.0.1":              {},
	"::1":                    {},
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
