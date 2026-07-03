package auth

import "testing"

func TestBuildLoginURLIncludesRelaySource(t *testing.T) {
	loginURL := BuildLoginURL("https://mdtero.com", "http://127.0.0.1:4173/callback", "state-1")
	if loginURL == "" {
		t.Fatal("expected login url")
	}
	if want := "source=relay"; !contains(loginURL, want) {
		t.Fatalf("expected %q in %q", want, loginURL)
	}
	if want := "cli_callback="; !contains(loginURL, want) {
		t.Fatalf("expected %q in %q", want, loginURL)
	}
}

func contains(haystack, needle string) bool {
	return len(haystack) >= len(needle) && (haystack == needle || len(needle) == 0 || indexOf(haystack, needle) >= 0)
}

func indexOf(s, sub string) int {
	for i := 0; i+len(sub) <= len(s); i++ {
		if s[i:i+len(sub)] == sub {
			return i
		}
	}
	return -1
}
