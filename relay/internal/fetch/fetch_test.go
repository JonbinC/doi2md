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

func TestElsevierCredentialsOnlySentToElsevierAPI(t *testing.T) {
	client := newHTTPClient(5 * time.Second)
	prev, _ := http.NewRequest(http.MethodGet, "https://api.elsevier.com/content/article/doi/10.1/x", nil)
	next, _ := http.NewRequest(http.MethodGet, "https://www.sciencedirect.com/science/article/pii/X", nil)
	next.Header.Set("X-ELS-APIKey", "k")
	next.Header.Set("X-ELS-Insttoken", "t")
	next.Header.Set("Accept", "text/xml")
	if err := client.CheckRedirect(next, []*http.Request{prev}); err != nil {
		t.Fatalf("unexpected redirect error: %v", err)
	}
	if next.Header.Get("X-ELS-APIKey") != "" || next.Header.Get("X-ELS-Insttoken") != "" {
		t.Fatal("Elsevier credentials leaked to cross-host redirect")
	}
	if next.Header.Get("Accept") != "text/xml" {
		t.Fatal("non-credential header should be kept")
	}

	same, _ := http.NewRequest(http.MethodGet, "https://api.elsevier.com/content/article/pii/X", nil)
	same.Header.Set("X-ELS-APIKey", "k")
	stripElsevierCredentials(same)
	if same.Header.Get("X-ELS-APIKey") != "k" {
		t.Fatal("credentials should be kept for https://api.elsevier.com")
	}
	for _, raw := range []string{"http://api.elsevier.com/x", "https://api.elsevier.com.evil.test/x", "https://api.elsevier.com:8443/x"} {
		r, _ := http.NewRequest(http.MethodGet, raw, nil)
		r.Header.Set("X-ELS-APIKey", "k")
		stripElsevierCredentials(r)
		if r.Header.Get("X-ELS-APIKey") != "" {
			t.Fatalf("credentials should be stripped for %s", raw)
		}
	}
}
