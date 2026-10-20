package campus

import "testing"

func TestSummarizeReportsEgressIP(t *testing.T) {
	s := summarize(map[string]any{"ip": "128.243.52.195", "city": "Nottingham"})
	if s.EgressIP != "128.243.52.195" || s.IP != "128.243.52.195" {
		t.Fatalf("unexpected summary: %+v", s)
	}
}
