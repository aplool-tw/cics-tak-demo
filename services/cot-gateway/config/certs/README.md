# Gateway Client Certificates

Place `gateway.p12` here (PKCS#12 bundle with client cert + private key issued by TAK Server CA).
Set password via env: `export TAK_P12_PASSWORD=your-password`.

## Alternative: offline PEM conversion

```bash
openssl pkcs12 -in gateway.p12 -out gateway.pem -nodes
```

Then point `tak_server.cert_file` at `gateway.pem` in `config/gateway.yaml`. This avoids the
`cryptography` dependency path (stdlib `ssl` loads PEM directly).

See research.md §R2 for rationale.
