package campus

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

const checkURL = "https://ifconfig.co/json"

type OutletSummary struct {
	IP     string `json:"ip,omitempty"`
	ASN    string `json:"asn,omitempty"`
	ASNOrg string `json:"asn_org,omitempty"`
	City   string `json:"city,omitempty"`
	Country string `json:"country,omitempty"`
}

type CheckResult struct {
	Summary  OutletSummary `json:"summary"`
	CampusOK bool          `json:"campus_ok"`
}

func Check(timeout time.Duration) (CheckResult, error) {
	client := &http.Client{Timeout: timeout}
	resp, err := client.Get(checkURL)
	if err != nil {
		return CheckResult{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		body, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return CheckResult{}, fmt.Errorf("campus outlet check failed: HTTP %d: %s", resp.StatusCode, strings.TrimSpace(string(body)))
	}
	var payload map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&payload); err != nil {
		return CheckResult{}, err
	}
	summary := summarize(payload)
	return CheckResult{
		Summary:  summary,
		CampusOK: isExpectedCampusOutlet(payload),
	}, nil
}

func summarize(payload map[string]any) OutletSummary {
	summary := OutletSummary{}
	if v, ok := payload["ip"].(string); ok {
		summary.IP = v
	}
	if v, ok := payload["asn"].(string); ok {
		summary.ASN = v
	}
	if v, ok := payload["asn_org"].(string); ok {
		summary.ASNOrg = v
	} else if v, ok := payload["org"].(string); ok {
		summary.ASNOrg = v
	}
	if v, ok := payload["city"].(string); ok {
		summary.City = v
	}
	if v, ok := payload["country"].(string); ok {
		summary.Country = v
	}
	return summary
}

func isExpectedCampusOutlet(payload map[string]any) bool {
	asn := strings.ToUpper(fmt.Sprint(payload["asn"]))
	org := strings.ToLower(fmt.Sprint(firstString(payload, "asn_org", "org")))
	city := strings.ToLower(fmt.Sprint(payload["city"]))
	return asn == "AS786" && strings.Contains(org, "jisc") && city == "nottingham"
}

func firstString(payload map[string]any, keys ...string) any {
	for _, key := range keys {
		if value, ok := payload[key]; ok {
			return value
		}
	}
	return ""
}
