package fetch

import (
	"encoding/base64"
	"errors"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/mdtero/mdtero-relay/internal/domains"
)

const MaxBodyBytes = 32 * 1024 * 1024
const MaxRedirects = 10

type Result struct {
	StatusCode int
	Headers    map[string]string
	BodyB64    string
	Error      string
	ReasonCode string
}

type redirectBlockedError struct {
	reason string
}

func (e redirectBlockedError) Error() string {
	if e.reason == "relay_fetch_too_many_redirects" {
		return "relay fetch exceeded the maximum redirect count"
	}
	return "relay redirect target is not an approved research publisher domain"
}

var newHTTPClient = func(timeout time.Duration) *http.Client {
	return &http.Client{
		Timeout: timeout,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			if len(via) >= MaxRedirects {
				return redirectBlockedError{reason: "relay_fetch_too_many_redirects"}
			}
			if reason := domains.RejectionReason(req.URL.String()); reason != "" {
				return redirectBlockedError{reason: reason}
			}
			return nil
		},
	}
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
	client := newHTTPClient(timeout)
	req, err := http.NewRequest(method, rawURL, nil)
	if err != nil {
		return Result{Error: err.Error(), ReasonCode: "relay_fetch_failed"}
	}
	for key, value := range headers {
		req.Header.Set(key, value)
	}
	resp, err := client.Do(req)
	if err != nil {
		var blocked redirectBlockedError
		if errors.As(err, &blocked) {
			return Result{Error: blocked.Error(), ReasonCode: blocked.reason}
		}
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
