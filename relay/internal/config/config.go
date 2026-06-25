package config

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
)

const (
	DefaultAPIBase = "https://api.mdtero.com"
	EnvAPIKey      = "MDTERO_API_KEY"
	EnvAPIBase     = "MDTERO_API_URL"
)

type Config struct {
	APIKey     string `json:"api_key"`
	APIBaseURL string `json:"api_base_url"`
	Label      string `json:"label,omitempty"`
}

func Dir() (string, error) {
	if override := strings.TrimSpace(os.Getenv("MDTERO_RELAY_CONFIG_DIR")); override != "" {
		return filepath.Abs(override)
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	if strings.EqualFold(os.Getenv("OS"), "Windows_NT") {
		base := os.Getenv("APPDATA")
		if base == "" {
			base = filepath.Join(home, "AppData", "Roaming")
		}
		return filepath.Join(base, "mdtero-relay"), nil
	}
	if xdg := strings.TrimSpace(os.Getenv("XDG_CONFIG_HOME")); xdg != "" {
		return filepath.Join(xdg, "mdtero-relay"), nil
	}
	return filepath.Join(home, ".config", "mdtero-relay"), nil
}

func Path() (string, error) {
	dir, err := Dir()
	if err != nil {
		return "", err
	}
	return filepath.Join(dir, "config.json"), nil
}

func Load() (Config, error) {
	cfg := Config{APIBaseURL: DefaultAPIBase}
	if key := strings.TrimSpace(os.Getenv(EnvAPIKey)); key != "" {
		cfg.APIKey = key
	}
	if base := strings.TrimSpace(os.Getenv(EnvAPIBase)); base != "" {
		cfg.APIBaseURL = strings.TrimRight(base, "/")
	}

	path, err := Path()
	if err != nil {
		return cfg, err
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return cfg, nil
		}
		return cfg, err
	}
	var file Config
	if err := json.Unmarshal(raw, &file); err != nil {
		return cfg, err
	}
	if cfg.APIKey == "" {
		cfg.APIKey = strings.TrimSpace(file.APIKey)
	}
	if cfg.APIBaseURL == DefaultAPIBase && strings.TrimSpace(file.APIBaseURL) != "" {
		cfg.APIBaseURL = strings.TrimRight(strings.TrimSpace(file.APIBaseURL), "/")
	}
	cfg.Label = strings.TrimSpace(file.Label)
	return cfg, nil
}

func Save(cfg Config) error {
	dir, err := Dir()
	if err != nil {
		return err
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return err
	}
	payload, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	path := filepath.Join(dir, "config.json")
	if err := os.WriteFile(path, append(payload, '\n'), 0o600); err != nil {
		return err
	}
	return nil
}

func (c Config) Authenticated() bool {
	return strings.TrimSpace(c.APIKey) != ""
}

func WSURL(apiBase string) string {
	base := strings.TrimRight(strings.TrimSpace(apiBase), "/")
	switch {
	case strings.HasPrefix(base, "https://"):
		return "wss://" + strings.TrimPrefix(base, "https://") + "/api/v1/relay/ws"
	case strings.HasPrefix(base, "http://"):
		return "ws://" + strings.TrimPrefix(base, "http://") + "/api/v1/relay/ws"
	default:
		return base + "/api/v1/relay/ws"
	}
}
