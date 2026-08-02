package browserfetch

import (
	"context"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestPreparePostsOnlyURLAndTimeout(t *testing.T) {
	var gotMethod, gotPath, gotAuth, gotBody string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotMethod = r.Method
		gotPath = r.URL.Path
		gotAuth = r.Header.Get("Authorization")
		payload, _ := io.ReadAll(r.Body)
		gotBody = string(payload)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ready"}`))
	}))
	defer server.Close()

	client := &Client{baseURL: server.URL, token: "local-token", http: server.Client()}
	result := client.Prepare(context.Background(), "https://ieeexplore.ieee.org/document/9845400", 30*time.Second)

	if result.Error != "" || result.ReasonCode != "" {
		t.Fatalf("unexpected prepare result: %#v", result)
	}
	if gotMethod != http.MethodPost || gotPath != "/v1/prepare" {
		t.Fatalf("unexpected request: %s %s", gotMethod, gotPath)
	}
	if gotAuth != "Bearer local-token" {
		t.Fatalf("unexpected auth header: %q", gotAuth)
	}
	if !strings.Contains(gotBody, `"url":"https://ieeexplore.ieee.org/document/9845400"`) || !strings.Contains(gotBody, `"timeout":30`) {
		t.Fatalf("unexpected payload: %s", gotBody)
	}
	if strings.Contains(gotBody, "recipe") {
		t.Fatalf("prepare must not send a capture recipe: %s", gotBody)
	}
}

func TestPrepareNeedsConfiguredClient(t *testing.T) {
	result := (&Client{}).Prepare(context.Background(), "https://ieeexplore.ieee.org/document/9845400", time.Second)
	if result.ReasonCode != "browser_relay_unavailable" {
		t.Fatalf("unexpected result: %#v", result)
	}
}

func TestFetchAcceptsFulltextRecipe(t *testing.T) {
	client := &Client{baseURL: "http://127.0.0.1:8788", token: "local-token", http: &http.Client{}}
	// Validation happens before the request, so no local service is needed.
	result := client.Fetch(context.Background(), "article_fulltext", "https://ieeexplore.ieee.org/document/9845400", time.Second)
	if result.ReasonCode == "browser_recipe_not_allowed" {
		t.Fatalf("fulltext recipe must be accepted: %#v", result)
	}
}

func TestHealthDoesNotExposeWorkerConfiguration(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet || r.URL.Path != "/health" {
			t.Fatalf("unexpected health request: %s %s", r.Method, r.URL.Path)
		}
		if got := r.Header.Get("Authorization"); got != "Bearer local-token" {
			t.Fatalf("unexpected auth header: %q", got)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ok","session_active":true,"worker_url":"http://127.0.0.1:8788"}`))
	}))
	defer server.Close()

	client := &Client{baseURL: server.URL, token: "local-token", http: server.Client()}
	health := client.Health(context.Background())
	if !health.Configured || !health.Reachable || !health.SessionActive || health.Status != "ok" {
		t.Fatalf("unexpected health: %#v", health)
	}
}

func TestHealthReportsUnconfiguredWorker(t *testing.T) {
	health := (*Client)(nil).Health(context.Background())
	if health.Configured || health.Reachable || health.Status != "not_configured" {
		t.Fatalf("unexpected health: %#v", health)
	}
}

func TestFromEnvRejectsRemoteWorkerEndpoint(t *testing.T) {
	t.Setenv(EnvWorkerURL, "https://worker.example.test")
	t.Setenv(EnvWorkerToken, "local-token")
	if client := FromEnv(); client != nil {
		t.Fatal("browser worker token must not be sent to a remote endpoint")
	}
}
