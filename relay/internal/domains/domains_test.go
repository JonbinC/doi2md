package domains

import "testing"

func TestAllowedPublisherURL(t *testing.T) {
	if !Allowed("https://doi.org/10.1038/nature12373") {
		t.Fatal("expected doi.org to be allowed")
	}
	if !Allowed("https://pubs.acs.org/doi/pdf/10.1021/demo") {
		t.Fatal("expected pubs.acs.org to be allowed")
	}
	if !Allowed("https://pubs.rsc.org/en/content/articlelanding/2025/ra/d5ra09148a") {
		t.Fatal("expected pubs.rsc.org to be allowed")
	}
	if !Allowed("https://mdpi-res.com/d_attachment/energies/energies-18-02643/article_deploy/energies-18-02643-v2.pdf") {
		t.Fatal("expected mdpi-res.com to be allowed")
	}
	if !Allowed("https://api.wiley.com/onlinelibrary/tdm/v1/articles/10.1002%2Fdemo") {
		t.Fatal("expected api.wiley.com to be allowed")
	}
	if !Allowed("https://journals.sagepub.com/doi/pdf/10.1177/example") {
		t.Fatal("expected journals.sagepub.com to be allowed")
	}
	if !Allowed("https://www.annualreviews.org/doi/pdf/10.1146/example") {
		t.Fatal("expected annualreviews.org to be allowed")
	}
}

func TestBlocksLocalhost(t *testing.T) {
	if Allowed("http://127.0.0.1/article") {
		t.Fatal("expected localhost to be blocked")
	}
	if RejectionReason("http://127.0.0.1/article") != "relay_url_private_host_blocked" {
		t.Fatalf("unexpected rejection reason: %s", RejectionReason("http://127.0.0.1/article"))
	}
}

func TestBlocksUnknownDomain(t *testing.T) {
	if Allowed("https://example.com/paper.pdf") {
		t.Fatal("expected example.com to be blocked")
	}
}
