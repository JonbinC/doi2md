package browserfetch

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const (
	EnvWorkerURL   = "MDTERO_BROWSER_WORKER_URL"
	EnvWorkerToken = "MDTERO_BROWSER_WORKER_TOKEN"
)

type Result struct {
	StatusCode int               `json:"status_code"`
	Headers    map[string]string `json:"headers"`
	BodyB64    string            `json:"body_b64"`
	Error      string            `json:"error"`
	ReasonCode string            `json:"reason_code"`
}

type Client struct {
	baseURL string
	token   string
	http    *http.Client
}

type localConfig struct {
	WorkerURL string `json:"worker_url"`
	Token     string `json:"token"`
}

func FromEnv() *Client {
	endpoint := strings.TrimRight(strings.TrimSpace(os.Getenv(EnvWorkerURL)), "/")
	token := strings.TrimSpace(os.Getenv(EnvWorkerToken))
	if endpoint == "" || token == "" {
		configuredEndpoint, configuredToken := loadLocalConfig()
		if endpoint == "" {
			endpoint = configuredEndpoint
		}
		if token == "" {
			token = configuredToken
		}
	}
	if endpoint == "" || token == "" {
		return nil
	}
	return &Client{
		baseURL: endpoint,
		token:   token,
		http:    &http.Client{Timeout: 125 * time.Second},
	}
}

func loadLocalConfig() (string, string) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", ""
	}
	path := filepath.Join(home, ".config", "mdtero-relay", "browser-worker.json")
	content, err := os.ReadFile(path)
	if err != nil {
		return "", ""
	}
	var cfg localConfig
	if err := json.Unmarshal(content, &cfg); err != nil {
		return "", ""
	}
	return strings.TrimRight(strings.TrimSpace(cfg.WorkerURL), "/"), strings.TrimSpace(cfg.Token)
}

func (c *Client) Enabled() bool {
	return c != nil && c.baseURL != "" && c.token != ""
}

func (c *Client) Fetch(ctx context.Context, recipe, rawURL string, timeout time.Duration) Result {
	if !c.Enabled() {
		return Result{Error: "Browser capture is not configured on this relay.", ReasonCode: "browser_relay_unavailable"}
	}
	recipe = strings.TrimSpace(recipe)
	if recipe != "article_html" && recipe != "article_pdf" && recipe != "article_fulltext" {
		return Result{Error: "Unsupported browser capture recipe.", ReasonCode: "browser_recipe_not_allowed"}
	}
	payload, err := json.Marshal(map[string]any{
		"recipe":  recipe,
		"url":     strings.TrimSpace(rawURL),
		"timeout": max(5, min(int(timeout.Seconds()), 120)),
	})
	if err != nil {
		return Result{Error: err.Error(), ReasonCode: "browser_relay_failed"}
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/v1/fetch", bytes.NewReader(payload))
	if err != nil {
		return Result{Error: err.Error(), ReasonCode: "browser_relay_failed"}
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	response, err := c.http.Do(req)
	if err != nil {
		return Result{Error: err.Error(), ReasonCode: "browser_relay_failed"}
	}
	defer response.Body.Close()
	// The worker caps decoded artifacts at 30 MiB. Base64 expands that to 40 MiB;
	// retain a small envelope margin while rejecting an unexpectedly large reply.
	body, err := io.ReadAll(io.LimitReader(response.Body, 44*1024*1024))
	if err != nil {
		return Result{Error: err.Error(), ReasonCode: "browser_relay_failed"}
	}
	var result Result
	if err := json.Unmarshal(body, &result); err != nil {
		return Result{Error: fmt.Sprintf("Browser worker returned invalid JSON (HTTP %d).", response.StatusCode), ReasonCode: "browser_relay_invalid_response"}
	}
	if response.StatusCode >= 400 && result.ReasonCode == "" {
		result.ReasonCode = "browser_relay_failed"
	}
	if response.StatusCode >= 400 && result.Error == "" {
		result.Error = fmt.Sprintf("Browser worker returned HTTP %d.", response.StatusCode)
	}
	return result
}

// Prepare opens an allowlisted publisher page in the owner-controlled browser
// so the user can complete their own institution login or publisher challenge
// before a later article capture. It returns no browser session state.
func (c *Client) Prepare(ctx context.Context, rawURL string, timeout time.Duration) Result {
	if !c.Enabled() {
		return Result{Error: "Browser capture is not configured on this relay.", ReasonCode: "browser_relay_unavailable"}
	}
	payload, err := json.Marshal(map[string]any{
		"url":     strings.TrimSpace(rawURL),
		"timeout": max(5, min(int(timeout.Seconds()), 120)),
	})
	if err != nil {
		return Result{Error: err.Error(), ReasonCode: "browser_relay_failed"}
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+"/v1/prepare", bytes.NewReader(payload))
	if err != nil {
		return Result{Error: err.Error(), ReasonCode: "browser_relay_failed"}
	}
	req.Header.Set("Authorization", "Bearer "+c.token)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	response, err := c.http.Do(req)
	if err != nil {
		return Result{Error: err.Error(), ReasonCode: "browser_relay_failed"}
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 64*1024))
	if err != nil {
		return Result{Error: err.Error(), ReasonCode: "browser_relay_failed"}
	}
	var result Result
	if err := json.Unmarshal(body, &result); err != nil {
		return Result{Error: fmt.Sprintf("Browser worker returned invalid JSON (HTTP %d).", response.StatusCode), ReasonCode: "browser_relay_invalid_response"}
	}
	if response.StatusCode >= 400 && result.ReasonCode == "" {
		result.ReasonCode = "browser_relay_failed"
	}
	if response.StatusCode >= 400 && result.Error == "" {
		result.Error = fmt.Sprintf("Browser worker returned HTTP %d.", response.StatusCode)
	}
	return result
}
