package auth

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"time"
)

const defaultSiteBase = "https://mdtero.com"

type LoginResult struct {
	APIKey string
	Prefix string
}

func SiteBaseURL() string {
	if value := strings.TrimSpace(os.Getenv("MDTERO_SITE_URL")); value != "" {
		return strings.TrimRight(value, "/")
	}
	return defaultSiteBase
}

func BuildLoginURL(siteBase, callbackURL, state string) string {
	params := url.Values{}
	params.Set("cli_callback", callbackURL)
	params.Set("cli_state", state)
	params.Set("source", "relay")
	return fmt.Sprintf("%s/auth?%s", strings.TrimRight(siteBase, "/"), params.Encode())
}

func WebLogin(timeout time.Duration) (LoginResult, error) {
	if timeout <= 0 {
		timeout = 3 * time.Minute
	}
	state, err := randomState()
	if err != nil {
		return LoginResult{}, err
	}

	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return LoginResult{}, err
	}
	defer listener.Close()

	resultCh := make(chan LoginResult, 1)
	errCh := make(chan error, 1)

	mux := http.NewServeMux()
	mux.HandleFunc("/callback", func(w http.ResponseWriter, r *http.Request) {
		origin := strings.TrimSpace(r.Header.Get("Origin"))
		if origin == "" {
			origin = SiteBaseURL()
		}
		if !allowedCallbackOrigin(origin) {
			http.Error(w, "origin not allowed", http.StatusForbidden)
			return
		}
		if r.Method == http.MethodOptions {
			w.Header().Set("Access-Control-Allow-Origin", origin)
			w.Header().Set("Access-Control-Allow-Methods", "POST, OPTIONS")
			w.Header().Set("Access-Control-Allow-Headers", "Content-Type")
			w.WriteHeader(http.StatusNoContent)
			return
		}
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		body, readErr := io.ReadAll(io.LimitReader(r.Body, 1<<20))
		if readErr != nil {
			errCh <- readErr
			return
		}
		var payload struct {
			State  string `json:"state"`
			APIKey string `json:"apiKey"`
			Prefix string `json:"prefix"`
		}
		if unmarshalErr := json.Unmarshal(body, &payload); unmarshalErr != nil {
			errCh <- unmarshalErr
			return
		}
		if strings.TrimSpace(payload.State) != state {
			errCh <- fmt.Errorf("invalid relay login state")
			return
		}
		apiKey := strings.TrimSpace(payload.APIKey)
		if apiKey == "" {
			errCh <- fmt.Errorf("relay login callback did not include an API key")
			return
		}
		w.Header().Set("Access-Control-Allow-Origin", origin)
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"ok": true})
		resultCh <- LoginResult{APIKey: apiKey, Prefix: strings.TrimSpace(payload.Prefix)}
	})

	server := &http.Server{Handler: mux}
	go func() {
		_ = server.Serve(listener)
	}()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	defer func() { _ = server.Shutdown(shutdownCtx) }()

	callbackURL := fmt.Sprintf("http://127.0.0.1:%d/callback", listener.Addr().(*net.TCPAddr).Port)
	loginURL := BuildLoginURL(SiteBaseURL(), callbackURL, state)
	if openErr := openBrowser(loginURL); openErr != nil {
		fmt.Println("Open this URL in your browser to sign in:")
		fmt.Println(loginURL)
	}

	select {
	case result := <-resultCh:
		return result, nil
	case err := <-errCh:
		return LoginResult{}, err
	case <-time.After(timeout):
		return LoginResult{}, fmt.Errorf("timed out waiting for Mdtero web login")
	}
}

func randomState() (string, error) {
	raw := make([]byte, 18)
	if _, err := rand.Read(raw); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(raw), nil
}

func openBrowser(target string) error {
	switch runtime.GOOS {
	case "darwin":
		return exec.Command("open", target).Start()
	case "windows":
		return exec.Command("rundll32", "url.dll,FileProtocolHandler", target).Start()
	default:
		if path, err := exec.LookPath("xdg-open"); err == nil {
			return exec.Command(path, target).Start()
		}
	}
	return fmt.Errorf("could not open browser automatically")
}

func allowedCallbackOrigin(origin string) bool {
	switch strings.TrimRight(strings.TrimSpace(origin), "/") {
	case "https://mdtero.com", "https://www.mdtero.com", "http://localhost:5173", "http://127.0.0.1:5173":
		return true
	default:
		return false
	}
}
