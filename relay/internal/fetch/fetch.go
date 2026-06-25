package fetch

import (
	"encoding/base64"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/mdtero/mdtero-relay/internal/domains"
)

const MaxBodyBytes = 32 * 1024 * 1024

type Result struct {
	StatusCode int
	Headers    map[string]string
	BodyB64    string
	Error      string
	ReasonCode string
}

func Execute(rawURL, method string, headers map[string]string, timeout time.Duration) Result {
	if reason := domains.RejectionReason(rawURL); reason != "" {
		return Result{
			Error:      "Relay fetch is limited to approved research publisher domains over HTTP/HTTPS.",
			ReasonCode: reason,
		}
	}
	method = strings.ToUpper(strings.TrimSpace(method))
	if method == "" {
		method = http.MethodGet
	}
	client := &http.Client{Timeout: timeout}
	req, err := http.NewRequest(method, rawURL, nil)
	if err != nil {
		return Result{Error: err.Error(), ReasonCode: "relay_fetch_failed"}
	}
	for key, value := range headers {
		req.Header.Set(key, value)
	}
	resp, err := client.Do(req)
	if err != nil {
		return Result{Error: err.Error(), ReasonCode: "relay_fetch_failed"}
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, MaxBodyBytes+1))
	if err != nil {
		return Result{Error: err.Error(), ReasonCode: "relay_fetch_failed"}
	}
	if len(body) > MaxBodyBytes {
		return Result{
			Error:      "Relay response exceeded the maximum allowed body size.",
			ReasonCode: "relay_fetch_body_too_large",
		}
	}
	headerMap := map[string]string{}
	for key, values := range resp.Header {
		if len(values) > 0 {
			headerMap[key] = values[0]
		}
	}
	return Result{
		StatusCode: resp.StatusCode,
		Headers:    headerMap,
		BodyB64:    base64.StdEncoding.EncodeToString(body),
	}
}
