package browserworker

// The browser worker is a small, local-only Playwright sidecar.  The native
// Relay owns its lifecycle so the user only installs one component; the
// Python worker never receives the Mdtero API key and never leaves loopback.

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

const (
	workerPort = "8788"
	workerURL  = "http://127.0.0.1:" + workerPort
)

type Status struct {
	Status      string `json:"status"`
	Configured  bool   `json:"configured"`
	Installed   bool   `json:"installed"`
	WorkerReady bool   `json:"worker_ready"`
}

type localConfig struct {
	WorkerURL string `json:"worker_url"`
	Token     string `json:"token"`
}

type Handle struct {
	cmd *exec.Cmd
}

func dataDir() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	if runtime.GOOS == "windows" {
		base := strings.TrimSpace(os.Getenv("LOCALAPPDATA"))
		if base == "" {
			base = filepath.Join(home, "AppData", "Local")
		}
		return filepath.Join(base, "Mdtero", "relay"), nil
	}
	base := strings.TrimSpace(os.Getenv("XDG_DATA_HOME"))
	if base == "" {
		base = filepath.Join(home, ".local", "share")
	}
	return filepath.Join(base, "mdtero-relay"), nil
}

func configPath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	if runtime.GOOS == "windows" {
		base := strings.TrimSpace(os.Getenv("APPDATA"))
		if base == "" {
			base = filepath.Join(home, "AppData", "Roaming")
		}
		return filepath.Join(base, "mdtero-relay", "browser-worker.json"), nil
	}
	base := strings.TrimSpace(os.Getenv("XDG_CONFIG_HOME"))
	if base == "" {
		base = filepath.Join(home, ".config")
	}
	return filepath.Join(base, "mdtero-relay", "browser-worker.json"), nil
}

func bundleDir() (string, error) {
	if override := strings.TrimSpace(os.Getenv("MDTERO_BROWSER_WORKER_DIR")); override != "" {
		return filepath.Abs(override)
	}
	root, err := dataDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(root, "browser_worker"), nil
}

func venvDir() (string, error) {
	root, err := dataDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(root, "browser-venv"), nil
}

func venvPython() (string, error) {
	venv, err := venvDir()
	if err != nil {
		return "", err
	}
	if runtime.GOOS == "windows" {
		return filepath.Join(venv, "Scripts", "python.exe"), nil
	}
	return filepath.Join(venv, "bin", "python"), nil
}

func desktop() bool {
	if truthy(os.Getenv("MDTERO_HEADLESS")) || truthy(os.Getenv("CI")) || truthy(os.Getenv("MDTERO_DISABLE_LOCAL_ACCESS")) {
		return false
	}
	if truthy(os.Getenv("MDTERO_FORCE_LOCAL_ACCESS")) {
		return true
	}
	if runtime.GOOS == "darwin" || runtime.GOOS == "windows" {
		return true
	}
	return strings.TrimSpace(os.Getenv("DISPLAY")) != "" || strings.TrimSpace(os.Getenv("WAYLAND_DISPLAY")) != ""
}

func truthy(value string) bool {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

func sourcePresent() bool {
	bundle, err := bundleDir()
	if err != nil {
		return false
	}
	for _, name := range []string{"mdtero_browser_worker.py", "requirements.txt"} {
		if _, err := os.Stat(filepath.Join(bundle, name)); err != nil {
			return false
		}
	}
	return true
}

func loadConfig() (localConfig, error) {
	path, err := configPath()
	if err != nil {
		return localConfig{}, err
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return localConfig{}, err
	}
	var cfg localConfig
	if err := json.Unmarshal(raw, &cfg); err != nil {
		return localConfig{}, err
	}
	if strings.TrimSpace(cfg.WorkerURL) != workerURL || strings.TrimSpace(cfg.Token) == "" {
		return localConfig{}, errors.New("invalid browser worker config")
	}
	return cfg, nil
}

func makeToken() (string, error) {
	buf := make([]byte, 32)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buf), nil
}

func ensureConfig() error {
	path, err := configPath()
	if err != nil {
		return err
	}
	if existing, err := loadConfig(); err == nil && existing.Token != "" {
		return nil
	}
	token, err := makeToken()
	if err != nil {
		return err
	}
	cfg := localConfig{WorkerURL: workerURL, Token: token}
	payload, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, append(payload, '\n'), 0o600); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

func findPython() (string, error) {
	for _, name := range func() []string {
		if runtime.GOOS == "windows" {
			return []string{"py", "python"}
		}
		return []string{"python3", "python"}
	}() {
		if path, err := exec.LookPath(name); err == nil {
			return path, nil
		}
	}
	return "", errors.New("Python 3 is required for local browser access")
}

func run(command string, args ...string) error {
	cmd := exec.Command(command, args...)
	cmd.Stdout = nil
	cmd.Stderr = nil
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("%s: %w", filepath.Base(command), err)
	}
	return nil
}

func Ensure() (Status, error) {
	if !desktop() {
		return Status{Status: "not_applicable"}, nil
	}
	if !sourcePresent() {
		return Status{Status: "unavailable"}, errors.New("browser worker bundle is not installed")
	}
	python, err := findPython()
	if err != nil {
		return Status{Status: "unavailable"}, err
	}
	venv, err := venvDir()
	if err != nil {
		return Status{Status: "unavailable"}, err
	}
	venvPy, err := venvPython()
	if err != nil {
		return Status{Status: "unavailable"}, err
	}
	if _, err := os.Stat(venvPy); err != nil {
		if err := os.MkdirAll(filepath.Dir(venvPy), 0o700); err != nil {
			return Status{Status: "unavailable"}, err
		}
		args := []string{"-m", "venv", venv}
		if runtime.GOOS == "windows" && filepath.Base(python) == "py" {
			args = []string{"-3", "-m", "venv", venv}
		}
		if err := run(python, args...); err != nil {
			return Status{Status: "unavailable"}, err
		}
	}
	bundle, _ := bundleDir()
	requirements := filepath.Join(bundle, "requirements.txt")
	marker := filepath.Join(venv, ".mdtero-worker-ready")
	if _, err := os.Stat(marker); err != nil {
		if err := run(venvPy, "-m", "pip", "install", "--disable-pip-version-check", "-r", requirements); err != nil {
			return Status{Status: "unavailable"}, err
		}
		// A managed browser is needed only when no ordinary Chrome/Edge binary is
		// available. Playwright's own browser is kept inside its cache.
		if !systemBrowserPresent() {
			if err := run(venvPy, "-m", "playwright", "install", "chromium"); err != nil {
				return Status{Status: "unavailable"}, err
			}
		}
		if err := os.WriteFile(marker, []byte("ready\n"), 0o600); err != nil {
			return Status{Status: "unavailable"}, err
		}
	}
	if err := ensureConfig(); err != nil {
		return Status{Status: "unavailable"}, err
	}
	return Status{Status: "ready", Configured: true, Installed: true}, nil
}

func systemBrowserPresent() bool {
	if runtime.GOOS == "darwin" {
		for _, path := range []string{
			"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
			"/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
			"/Applications/Chromium.app/Contents/MacOS/Chromium",
		} {
			if _, err := os.Stat(path); err == nil {
				return true
			}
		}
	}
	for _, name := range []string{"google-chrome", "google-chrome-stable", "microsoft-edge", "chromium", "chromium-browser", "chrome", "msedge"} {
		if _, err := exec.LookPath(name); err == nil {
			return true
		}
	}
	return false
}

func health(ctx context.Context) bool {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, workerURL+"/health", nil)
	if err != nil {
		return false
	}
	client := &http.Client{Timeout: 800 * time.Millisecond}
	response, err := client.Do(req)
	if err != nil {
		return false
	}
	defer response.Body.Close()
	return response.StatusCode < 400
}

func Start() (*Handle, error) {
	if !desktop() || !sourcePresent() {
		return nil, nil
	}
	if health(context.Background()) {
		return nil, nil
	}
	cfg, err := loadConfig()
	if err != nil {
		return nil, err
	}
	python, err := venvPython()
	if err != nil {
		return nil, err
	}
	if _, err := os.Stat(python); err != nil {
		return nil, err
	}
	bundle, err := bundleDir()
	if err != nil {
		return nil, err
	}
	cmd := exec.Command(python, filepath.Join(bundle, "mdtero_browser_worker.py"))
	cmd.Env = append(os.Environ(), "MDTERO_BROWSER_WORKER_CONFIG="+mustConfigPath(cfg))
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	for attempt := 0; attempt < 30; attempt++ {
		if health(context.Background()) {
			return &Handle{cmd: cmd}, nil
		}
		time.Sleep(100 * time.Millisecond)
	}
	_ = cmd.Process.Kill()
	_ = cmd.Wait()
	return nil, errors.New("browser worker did not become ready")
}

func mustConfigPath(_ localConfig) string {
	path, _ := configPath()
	return path
}

func (h *Handle) Stop() {
	if h == nil || h.cmd == nil || h.cmd.Process == nil {
		return
	}
	_ = h.cmd.Process.Kill()
	_ = h.cmd.Wait()
}

// BundleFilesExist is used by packaging tests and avoids exposing local paths.
func BundleFilesExist(root string) bool {
	for _, name := range []string{"mdtero_browser_worker.py", "requirements.txt"} {
		info, err := os.Stat(filepath.Join(root, name))
		if err != nil || info.IsDir() {
			return false
		}
	}
	return true
}
