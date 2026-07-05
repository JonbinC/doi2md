package client

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gorilla/websocket"
	"github.com/mdtero/mdtero-relay/internal/campus"
)

func TestRunOnceRegistersAndReturnsFetchResult(t *testing.T) {
	upgrader := websocket.Upgrader{}
	resultCh := make(chan map[string]any, 1)

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			t.Errorf("upgrade failed: %v", err)
			return
		}
		defer conn.Close()

		if err := conn.WriteJSON(map[string]any{"type": "hello", "user_id": 7}); err != nil {
			t.Errorf("write hello failed: %v", err)
			return
		}

		var register map[string]any
		if err := conn.ReadJSON(&register); err != nil {
			t.Errorf("read register failed: %v", err)
			return
		}
		if register["type"] != "register" {
			t.Errorf("unexpected register type: %v", register["type"])
			return
		}
		if register["label"] != "lab-mac" {
			t.Errorf("unexpected label: %v", register["label"])
			return
		}

		if err := conn.WriteJSON(map[string]any{"type": "registered", "relay_id": "relay-1"}); err != nil {
			t.Errorf("write registered failed: %v", err)
			return
		}
		if err := conn.WriteJSON(map[string]any{
			"type":       "fetch",
			"request_id": "req-1",
			"url":        "https://example.com/private.pdf",
			"method":     "GET",
			"headers":    map[string]any{},
			"timeout":    5,
		}); err != nil {
			t.Errorf("write fetch failed: %v", err)
			return
		}

		var result map[string]any
		if err := conn.ReadJSON(&result); err != nil {
			t.Errorf("read fetch_result failed: %v", err)
			return
		}
		resultCh <- result
	}))
	defer server.Close()

	wsURL := "ws" + strings.TrimPrefix(server.URL, "http")
	err := runOnce(
		wsURL,
		http.Header{"Authorization": []string{"ApiKey mdt_test"}},
		"lab-mac",
		campus.OutletSummary{ASN: "AS786", City: "Nottingham"},
		func(string, ...any) {},
	)
	if err == nil {
		t.Fatal("expected runOnce to return after server closes the websocket")
	}

	result := <-resultCh
	if result["type"] != "fetch_result" {
		t.Fatalf("unexpected result type: %v", result["type"])
	}
	if result["request_id"] != "req-1" {
		t.Fatalf("unexpected request id: %v", result["request_id"])
	}
	if result["reason_code"] != "relay_url_domain_not_allowed" {
		t.Fatalf("unexpected reason_code: %v", result["reason_code"])
	}
}
