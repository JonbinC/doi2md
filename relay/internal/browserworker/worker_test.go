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
}

func TestWorkerURLIsLoopback(t *testing.T) {
	if workerURL != "http://127.0.0.1:8788" {
		t.Fatalf("unexpected worker endpoint: %s", workerURL)
	}
}
