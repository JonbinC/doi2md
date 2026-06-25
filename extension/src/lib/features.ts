declare const __MDTERO_PROXY_ENABLED__: boolean | undefined;

export const PROXY_FEATURES_ENABLED =
  typeof __MDTERO_PROXY_ENABLED__ === "boolean" ? __MDTERO_PROXY_ENABLED__ : true;
