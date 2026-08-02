package domains

import (
	"net"
	"net/url"
	"strings"
)

var allowedSuffixes = []string{
	"aacrjournals.org",
	"academic.oup.com",
	"acm.org",
	"ahajournals.org",
	"aiaa.org",
	"annualreviews.org",
	"api.crossref.org",
	"api.elsevier.com",
	"api.openalex.org",
	"api.wiley.com",
	"arxiv.org",
	"arvojournals.org",
	"ashpublications.org",
	"asm.org",
	"asme.org",
	"aspetjournals.org",
	"atsjournals.org",
	"cancerbiomed.org",
	"cambridge.org",
	"cell.com",
	"crossref.org",
	"degruyter.com",
	"degruyterbrill.com",
	"diabetesjournals.org",
	"dl.acm.org",
	"doi.org",
	"elsevier.com",
	"emerald.com",
	"frontiersin.org",
	"ieeexplore.ieee.org",
	"ieee.org",
	"ingentaconnect.com",
	"jci.org",
	"journals.aps.org",
	"journals.uchicago.edu",
	"jstage.jst.go.jp",
	"jstor.org",
	"karger.com",
	"link.springer.com",
	"liebertpub.com",
	"lww.com",
	"mdpi.com",
	"mdpi-res.com",
	"nature.com",
	"ncbi.nlm.nih.gov",
	"nejm.org",
	"onlinelibrary.wiley.com",
	"openalex.org",
	"optica.org",
	"oup.com",
	"plos.org",
	"pnas.org",
	"pubs.acs.org",
	"pubs.rsc.org",
	"pubmed.ncbi.nlm.nih.gov",
	"rupress.org",
	"sagepub.com",
	"science.org",
	"sciencedirect.com",
	"sciendo.com",
	"siam.org",
	"spandidos-publications.com",
	"springer.com",
	"tandfonline.com",
	"thieme-connect.com",
	"wiley.com",
	"worldscientific.com",
}

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
