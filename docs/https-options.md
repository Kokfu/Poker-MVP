# HTTPS options for installing Poker Coach on a phone

A phone opens the PC’s LAN address as a remote origin. A trusted HTTPS
connection lets the browser treat it as a secure context and register the
service worker. Each hostname and port has its own site storage, so open and
install from the address you intend to keep. [Service Workers specification](https://www.w3.org/TR/service-workers/) [PWA installation guide](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable)

| Option | Setup on each phone | Where it works |
| --- | --- | --- |
| mkcert | Import and trust your local CA | Private Wi-Fi with a stable host name or IP |
| Tailscale Serve | Join the tailnet and use its HTTPS name | From devices permitted by tailnet access rules |
| Self-signed certificate | Import the certificate where the browser supports it | Private Wi-Fi with manual trust and renewal |

## mkcert

1. Reserve a LAN IP or use a local DNS name the phone can resolve. Generate a
   server certificate with mkcert for the name or IP you will type in the phone
   browser. Keep the private key on the PC.
2. Start Coach with `-LoopbackOnly`. Configure an HTTPS reverse proxy on the
   chosen Private interface, point it at `http://127.0.0.1:5173`, and provide
   the generated server certificate and key.
3. Transfer only `rootCA.pem` from the directory printed by `mkcert -CAROOT`.
   Install it on your own phone. On iOS, enable full trust in Certificate
   Trust Settings. Android's certificate menu and browser trust can vary by
   device. Open the HTTPS address and check that the browser accepts it.
   [mkcert mobile instructions](https://github.com/FiloSottile/mkcert#mobile-devices) [Apple trust settings](https://support.apple.com/en-ca/102390) [Pixel certificate settings](https://support.google.com/pixelphone/answer/2844832?hl=en)

Treat the local CA key as sensitive. A copied CA key can issue certificates
that a device trusting that root will accept. Remove the root from phones
when you stop using it. Changing the LAN IP requires a new certificate if
the certificate names that IP. [mkcert guidance](https://github.com/FiloSottile/mkcert#caution)

## Tailscale Serve

1. Join the PC and phone to the same tailnet. Allow only the intended devices
   or users to reach the PC's Serve endpoint and enable tailnet HTTPS.
2. Start Coach with `-LoopbackOnly`. On the PC, run `tailscale serve 5173`
   and use the HTTPS URL it prints on the phone. The foreground Serve
   session ends with Ctrl+C.
3. Keep the route scoped to Serve. Funnel has public Internet reachability.
   Review the tailnet access rules before sharing the URL. Issuing the
   certificate makes the HTTPS hostname visible in Certificate Transparency
   logs. [Serve documentation](https://tailscale.com/docs/features/tailscale-serve) [Tailnet HTTPS certificates](https://tailscale.com/docs/how-to/set-up-https-certificates)

## Self-signed certificate

1. Use your TLS tool to generate a short-lived server certificate and key with
   the exact DNS name or IP in the Subject Alternative Name. Configure the
   HTTPS proxy as in the mkcert option.
2. Import the public certificate where the phone and browser allow a
   manually trusted self-signed server certificate. Some trust stores
   require a CA certificate instead. In that case, use a local CA or a
   publicly trusted endpoint. Check the URL opens as a trusted origin before
   trying to install. [OpenSSL certificate options](https://docs.openssl.org/3.5/man1/openssl-req/) [Apple trust settings](https://support.apple.com/en-ca/102390)
3. Renew the certificate and update phone trust when it expires or the name
   changes. Keep the private key on the PC.

For any reverse proxy, browsers reach the same Coach API and saved-hand
store as the web interface. Allow access only to the intended devices. The
launcher currently uses the socket peer for rate limits, so proxied clients
can share a rate-limit bucket. These options are setup notes only.
