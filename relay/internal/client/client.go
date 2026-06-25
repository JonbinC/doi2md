package client

import (
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gorilla/websocket"
	"github.com/mdtero/mdtero-relay/internal/campus"
	"github.com/mdtero/mdtero-relay/internal/config"
	"github.com/mdtero/mdtero-relay/internal/fetch"
)

const reconnectDelay = 5 * time.Second

type Logger func(format string, args ...any)

type Options struct {
	Label  string
	Logger Logger
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
		return err
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
		if err := runOnce(wsURL, headers, label, outlet.Summary, logger); err != nil {
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

func runOnce(wsURL string, headers http.Header, label string, outlet campus.OutletSummary, logger Logger) error {
	dialer := websocket.Dialer{HandshakeTimeout: 20 * time.Second}
	conn, _, err := dialer.Dial(wsURL, headers)
	if err != nil {
		return err
	}
	defer conn.Close()

	logger("Connecting campus relay ...")

	var hello map[string]any
	if err := conn.ReadJSON(&hello); err != nil {
		return err
	}
	if fmt.Sprint(hello["type"]) != "hello" {
		return fmt.Errorf("relay handshake failed: expected hello")
	}

	register := map[string]any{
		"type":   "register",
		"label":  label,
		"outlet": outlet,
	}
	if err := conn.WriteJSON(register); err != nil {
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

	logger("Campus relay is live. Keep this running while cloud agents fetch papers.")
	logger("Press Ctrl+C to stop.")

	for {
		var message map[string]any
		if err := conn.ReadJSON(&message); err != nil {
			return err
		}
		switch fmt.Sprint(message["type"]) {
		case "ping":
			_ = conn.WriteJSON(map[string]string{"type": "pong"})
		case "fetch":
			response := handleFetch(message)
			if err := conn.WriteJSON(response); err != nil {
				return err
			}
		}
	}
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
