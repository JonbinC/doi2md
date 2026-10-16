package config

import "testing"

func TestNormalizeLocalBrowser(t *testing.T) {
	cases := map[string]string{
		"":                 LocalBrowserAuto,
		"auto":             LocalBrowserAuto,
		"HEADLESS":         LocalBrowserHeadless,
		"headless-browser": LocalBrowserHeadless,
		"off":              LocalBrowserOff,
		"false":            LocalBrowserOff,
	}
	for input, want := range cases {
		if got := NormalizeLocalBrowser(input); got != want {
			t.Fatalf("NormalizeLocalBrowser(%q)=%q want %q", input, got, want)
		}
	}
}
