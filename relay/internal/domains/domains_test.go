package domains

import "testing"

func TestAllowedPublisherURL(t *testing.T) {
	if !Allowed("https://doi.org/10.1038/nature12373") {
		t.Fatal("expected doi.org to be allowed")
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
