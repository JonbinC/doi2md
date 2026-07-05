package fetch

import (
	"net/http"
	"testing"
	"time"
)

func TestRedirectPolicyBlocksDisallowedTarget(t *testing.T) {
	client := newHTTPClient(5 * time.Second)
	redirectReq, err := http.NewRequest(http.MethodGet, "https://example.com/private.pdf", nil)
	if err != nil {
		t.Fatal(err)
	}
	previousReq, err := http.NewRequest(http.MethodGet, "https://doi.org/10.1038/nature12373", nil)
	if err != nil {
		t.Fatal(err)
	}

	err = client.CheckRedirect(redirectReq, []*http.Request{previousReq})
	if err == nil {
		t.Fatal("expected redirect rejection")
	}
	blocked, ok := err.(redirectBlockedError)
	if !ok {
		t.Fatalf("expected redirectBlockedError, got %T", err)
	}
	if blocked.reason != "relay_url_domain_not_allowed" {
		t.Fatalf("unexpected rejection reason: %s", blocked.reason)
	}
}
