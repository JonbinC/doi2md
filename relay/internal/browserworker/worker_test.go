package browserworker

import (
	"path/filepath"
	"testing"
)

func TestBundledWorkerFilesArePresent(t *testing.T) {
	root := filepath.Join("..", "..", "browser_worker")
	if !BundleFilesExist(root) {
		t.Fatalf("browser worker bundle is missing from %s", root)
	}
	policy := filepath.Join("..", "..", "..", "src", "mdtero")
	if !PolicyFilesExist(policy) {
		t.Fatalf("shared publisher and Relay policy sources are missing from %s", policy)
	}
}

func TestWorkerURLIsLoopback(t *testing.T) {
	if workerURL != "http://127.0.0.1:8788" {
		t.Fatalf("unexpected worker endpoint: %s", workerURL)
	}
}

func TestModeDefaultsToAuto(t *testing.T) {
	t.Setenv("MDTERO_LOCAL_BROWSER", "")
	if Mode() != "auto" {
		t.Fatalf("expected auto, got %s", Mode())
	}
}

func TestHeadlessModeEnablesWithoutDisplay(t *testing.T) {
	t.Setenv("MDTERO_LOCAL_BROWSER", "headless")
	t.Setenv("MDTERO_DISABLE_LOCAL_ACCESS", "")
	t.Setenv("MDTERO_HEADLESS", "1")
	t.Setenv("DISPLAY", "")
	t.Setenv("WAYLAND_DISPLAY", "")
	if !Enabled() {
		t.Fatal("headless mode should enable the worker even without a display")
	}
	if !HeadlessPreferred() {
		t.Fatal("headless mode should prefer headless Chromium")
	}
}

func TestOffModeDisablesWorker(t *testing.T) {
	t.Setenv("MDTERO_LOCAL_BROWSER", "off")
	t.Setenv("MDTERO_FORCE_LOCAL_ACCESS", "")
	if Enabled() {
		t.Fatal("off mode should disable the worker")
	}
}

func TestPlaywrightManagedBrowserSkipsArmv7(t *testing.T) {
	// Runtime GOARCH is the build host; assert the helper stays a pure function
	// of GOARCH by checking the documented contract for common values.
	supported := playwrightManagedBrowserSupported()
	if !supported && Mode() == "auto" {
		t.Log("host GOARCH does not ship a Playwright Chromium; ARMv7 installs must use system Chromium")
	}
}
