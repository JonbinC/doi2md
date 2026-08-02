package client

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/mdtero/mdtero-relay/internal/browserfetch"
	"github.com/mdtero/mdtero-relay/internal/campus"
	"github.com/mdtero/mdtero-relay/internal/config"
	"github.com/mdtero/mdtero-relay/internal/domains"
	"github.com/mdtero/mdtero-relay/internal/fetch"
)

const reconnectDelay = 5 * time.Second
const relayKeepaliveInterval = 20 * time.Second

type Logger func(format string, args ...any)

type Options struct {
	Label   string
	Logger  Logger
	Browser *browserfetch.Client
}

func DefaultLogger() Logger {
	return func(format string, args ...any) {
		log.Printf(format, args...)
	}
}

func Run(cfg config.Config, opts Options) error {
	if !cfg.Authenticated() {
		return fmt.Errorf("API key is missing. Run `mdtero-relay login --api-key <key>` first")
	}
	logger := opts.Logger
	if logger == nil {
		logger = DefaultLogger()
	}

	outlet, err := campus.Check(20 * time.Second)
	if err != nil {
		// Public IP/ASN lookup is diagnostic only.  A campus firewall, captive
		// portal, or transient outage must not prevent the outbound WebSocket
		// relay from starting; the publisher request itself is the source of
		// truth for whether this outlet can reach the article.
		logger("Campus network check unavailable: %v", err)
		outlet = campus.CheckResult{}
	}
	if outlet.CampusOK {
		logger("Campus network: ok (%s, %s)", outlet.Summary.ASN, outlet.Summary.City)
	} else {
		logger("Warning: this machine does not look like the expected campus outlet (%s, %s). Relay will still start, but publisher access may fail.", outlet.Summary.ASN, outlet.Summary.City)
	}

	wsURL := config.WSURL(cfg.APIBaseURL)
	headers := http.Header{}
	headers.Set("Authorization", "ApiKey "+strings.TrimSpace(cfg.APIKey))
	headers.Set("X-Client-Channel", "mdtero-relay")

	label := strings.TrimSpace(opts.Label)
	if label == "" {
		label = strings.TrimSpace(cfg.Label)
	}

	for {
		if err := runOnce(wsURL, headers, label, outlet.Summary, opts.Browser, logger); err != nil {
			if isStop(err) {
				return nil
			}
			logger("Relay error: %v", err)
			logger("Reconnecting in %s ...", reconnectDelay)
			time.Sleep(reconnectDelay)
			continue
		}
		logger("Relay disconnected. Reconnecting in %s ...", reconnectDelay)
		time.Sleep(reconnectDelay)
	}
}

func runOnce(wsURL string, headers http.Header, label string, outlet campus.OutletSummary, browser *browserfetch.Client, logger Logger) error {
	dialer := websocket.Dialer{HandshakeTimeout: 20 * time.Second}
	conn, _, err := dialer.Dial(wsURL, headers)
	if err != nil {
		return err
	}
	defer conn.Close()
	var writeMu sync.Mutex
	writeJSON := func(payload any) error {
		writeMu.Lock()
		defer writeMu.Unlock()
		_ = conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
		return conn.WriteJSON(payload)
	}

	logger("Connecting campus relay ...")

	var hello map[string]any
	if err := conn.ReadJSON(&hello); err != nil {
		return err
	}
	if fmt.Sprint(hello["type"]) != "hello" {
		return fmt.Errorf("relay handshake failed: expected hello")
	}

	capabilities := relayCapabilities(browser)
	if browser != nil && browser.Enabled() && len(capabilities) == 1 {
		logger("Browser capture is configured but its local worker is not reachable; continuing with campus HTTP relay.")
	}
	register := map[string]any{
		"type":         "register",
		"label":        label,
		"outlet":       outlet,
		"capabilities": capabilities,
	}
	if err := writeJSON(register); err != nil {
		return err
	}

	var registered map[string]any
	if err := conn.ReadJSON(&registered); err != nil {
		return err
	}
	if fmt.Sprint(registered["type"]) != "registered" {
		return fmt.Errorf("%s", firstNonEmpty(
			fmt.Sprint(registered["action_hint"]),
			fmt.Sprint(registered["reason_code"]),
			"relay registration failed",
		))
	}

	logger("Campus Relay is live. The background service will reconnect automatically.")
	// A campus relay can be idle for minutes between papers. Keep the WebSocket
	// active through proxies/CDNs without sending any article or session state.
	done := make(chan struct{})
	var keepalive sync.WaitGroup
	keepalive.Add(1)
	go func() {
		defer keepalive.Done()
		ticker := time.NewTicker(relayKeepaliveInterval)
		defer ticker.Stop()
		for {
			select {
			case <-done:
				return
			case <-ticker.C:
				if err := writeJSON(map[string]string{"type": "ping"}); err != nil {
					return
				}
			}
		}
	}()
	defer func() {
		close(done)
		keepalive.Wait()
	}()

	for {
		var message map[string]any
		if err := conn.ReadJSON(&message); err != nil {
			return err
		}
		switch fmt.Sprint(message["type"]) {
		case "ping":
			_ = writeJSON(map[string]string{"type": "pong"})
		case "fetch":
			response := handleFetch(message)
			if err := writeJSON(response); err != nil {
				return err
			}
		case "browser_fetch":
			response := handleBrowserFetch(message, browser)
			if err := writeJSON(response); err != nil {
				return err
			}
		}
	}
}

func relayCapabilities(browser *browserfetch.Client) []string {
	capabilities := []string{"http_fetch"}
	if browser != nil && browser.Enabled() {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		health := browser.Health(ctx)
		cancel()
		if !health.Reachable {
			return capabilities
		}
		// This one bounded operation prefers PDF and falls back to sanitized
		// article HTML, so an intermittent websocket reconnect cannot split the
		// two representations across separate requests.
		capabilities = append(capabilities, "browser_fetch", "browser_fulltext")
	}
	return capabilities
}

func handleFetch(message map[string]any) map[string]any {
	requestID := fmt.Sprint(message["request_id"])
	rawURL := fmt.Sprint(message["url"])
	method := fmt.Sprint(message["method"])
	timeoutSeconds := 60.0
	if value, ok := message["timeout"].(float64); ok && value > 0 {
		timeoutSeconds = value
	}
	headers := map[string]string{}
	if raw, ok := message["headers"].(map[string]any); ok {
		for key, value := range raw {
			headers[key] = fmt.Sprint(value)
		}
	}

	result := fetch.Execute(rawURL, method, headers, time.Duration(timeoutSeconds)*time.Second)
	response := map[string]any{
		"type":       "fetch_result",
		"request_id": requestID,
	}
	if result.ReasonCode != "" || result.Error != "" {
		response["error"] = firstNonEmpty(result.Error, "Relay fetch failed.")
		response["reason_code"] = firstNonEmpty(result.ReasonCode, "relay_fetch_failed")
		return response
	}
	response["status_code"] = result.StatusCode
	response["headers"] = result.Headers
	response["body_b64"] = result.BodyB64
	return response
}

func handleBrowserFetch(message map[string]any, browser *browserfetch.Client) map[string]any {
	requestID := fmt.Sprint(message["request_id"])
	rawURL := fmt.Sprint(message["url"])
	recipe := fmt.Sprint(message["recipe"])
	timeoutSeconds := 90.0
	if value, ok := message["timeout"].(float64); ok && value > 0 {
		timeoutSeconds = value
	}
	response := map[string]any{
		"type":       "browser_fetch_result",
		"request_id": requestID,
	}
	if browser == nil || !browser.Enabled() {
		response["error"] = "Browser capture is not configured on this relay."
		response["reason_code"] = "browser_relay_unavailable"
		return response
	}
	if reason := domains.RejectionReason(rawURL); reason != "" {
		response["error"] = "Browser capture is limited to approved research publisher domains over HTTP/HTTPS."
		response["reason_code"] = reason
		return response
	}
	result := browser.Fetch(context.Background(), recipe, rawURL, time.Duration(timeoutSeconds)*time.Second)
	if result.ReasonCode != "" || result.Error != "" {
		response["error"] = firstNonEmpty(result.Error, "Browser capture failed.")
		response["reason_code"] = firstNonEmpty(result.ReasonCode, "browser_relay_failed")
		return response
	}
	response["status_code"] = result.StatusCode
	response["headers"] = result.Headers
	response["body_b64"] = result.BodyB64
	return response
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func isStop(err error) bool {
	return err == os.ErrClosed
}

func FetchStatus(cfg config.Config) (map[string]any, error) {
	if !cfg.Authenticated() {
		return nil, fmt.Errorf("API key is missing")
	}
	url := strings.TrimRight(cfg.APIBaseURL, "/") + "/api/v1/relay/status"
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "ApiKey "+strings.TrimSpace(cfg.APIKey))
	req.Header.Set("X-Client-Channel", "mdtero-relay")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var payload map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return nil, err
	}
	if resp.StatusCode >= 400 {
		return payload, fmt.Errorf("relay status failed: HTTP %d", resp.StatusCode)
	}
	return payload, nil
}
