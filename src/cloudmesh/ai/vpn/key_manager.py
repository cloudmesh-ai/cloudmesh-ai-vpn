import os
import subprocess
from typing import Any, Dict, Optional, List
from cloudmesh.ai.common.io import console

class KeyManager:
    """Handles validation and initialization of VPN certificates and keys."""

    @staticmethod
    def validate_keys(cert_path: str, key_path: str, ca_path: Optional[str]) -> Dict[str, Any]:
        """
        Verify VPN certificates and keys using openssl.
        
        Args:
            cert_path (str): Path to the user certificate (.crt).
            key_path (str): Path to the private key (.key).
            ca_path (str, optional): Path to the CA certificate (.cer).
            
        Returns:
            Dict containing the results of each check.
        """
        results = {
            "files_found": False,
            "expiration": {"status": "Unknown", "detail": ""},
            "integrity": {"status": "Unknown", "detail": ""},
            "match": {"status": "Unknown", "detail": ""},
            "trust": {"status": "Unknown", "detail": ""},
        }

        # 1. Check if required files exist
        for f in [cert_path, key_path]:
            if not f or not os.path.exists(os.path.expanduser(f)):
                results["files_found"] = False
                return results
        
        # CA is optional
        if ca_path and not os.path.exists(os.path.expanduser(ca_path)):
            results["trust"] = {"status": "FAILED", "detail": "CA file not found"}
        
        results["files_found"] = True

        cert = os.path.expanduser(cert_path)
        key = os.path.expanduser(key_path)
        ca = os.path.expanduser(ca_path) if ca_path else None

        def run_cmd(cmd):
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, check=False)
                return res.returncode, res.stdout.strip(), res.stderr.strip()
            except Exception as e:
                return 1, "", str(e)

        # 2. Expiration Check
        rc, out, err = run_cmd(["openssl", "x509", "-in", cert, "-noout", "-checkend", "0"])
        if rc == 0:
            # Get the actual date for the detail
            _, date, _ = run_cmd(["openssl", "x509", "-in", cert, "-noout", "-enddate"])
            results["expiration"] = {"status": "OK", "detail": date}
        else:
            results["expiration"] = {"status": "FAILED", "detail": "Certificate has expired"}

        # 3. Integrity Check
        rc, out, err = run_cmd(["openssl", "rsa", "-in", key, "-check"])
        if rc == 0 and "RSA key ok" in out:
            results["integrity"] = {"status": "OK", "detail": "Key is valid"}
        else:
            results["integrity"] = {"status": "FAILED", "detail": err or "Key is invalid"}

        # 4. Modulus Match Check
        _, cert_mod, _ = run_cmd(["openssl", "x509", "-noout", "-modulus", "-in", cert])
        _, key_mod, _ = run_cmd(["openssl", "rsa", "-noout", "-modulus", "-in", key])
        
        if cert_mod and key_mod and cert_mod == key_mod:
            results["match"] = {"status": "OK", "detail": "Key and Cert match"}
        else:
            results["match"] = {"status": "FAILED", "detail": "Key and Cert do NOT match"}

        # 5. Trust Chain Check
        if ca:
            rc, out, err = run_cmd(["openssl", "verify", "-CAfile", ca, cert])
            if rc == 0:
                results["trust"] = {"status": "OK", "detail": "Signed by CA"}
            else:
                results["trust"] = {"status": "FAILED", "detail": err or "Not signed by CA"}
        else:
            results["trust"] = {"status": "Unknown", "detail": "No CA provided"}

        return results

    @staticmethod
    def init_keys(p12_path: str, output_dir: str) -> bool:
        """
        Initialize VPN keys from a .p12 bundle.
        Extracts user.crt, user.key, and creates user_decrypted.pem.
        """
        p12 = os.path.expanduser(p12_path)
        out_dir = os.path.expanduser(output_dir)

        if not os.path.exists(p12):
            console.error(f"P12 file not found: {p12}")
            return False

        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            console.error(f"Failed to create output directory {out_dir}: {e}")
            return False

        cert_path = os.path.join(out_dir, "user.crt")
        key_path = os.path.join(out_dir, "user.key")
        pem_path = os.path.join(out_dir, "user_decrypted.pem")

        console.msg(f"Extracting keys from {p12} to {out_dir}...")

        # 1. Extract Certificate
        res_cert = subprocess.run(
            ["openssl", "pkcs12", "-in", p12, "-clcerts", "-nokeys", "-out", cert_path],
            capture_output=True, text=True
        )
        if res_cert.returncode != 0:
            console.error(f"Failed to extract certificate: {res_cert.stderr}")
            return False

        # 2. Extract Decrypted Private Key
        res_key = subprocess.run(
            ["openssl", "pkcs12", "-in", p12, "-nocerts", "-nodes", "-out", key_path],
            capture_output=True, text=True
        )
        if res_key.returncode != 0:
            console.error(f"Failed to extract private key: {res_key.stderr}")
            return False

        # 3. Create Decrypted PEM (Combined)
        try:
            with open(key_path, 'r') as f_key, open(cert_path, 'r') as f_cert:
                combined = f_key.read() + "\n" + f_cert.read()
            with open(pem_path, 'w') as f_pem:
                f_pem.write(combined)
        except Exception as e:
            console.error(f"Failed to create combined PEM file: {e}")
            return False

        # Set secure permissions
        for f in [key_path, pem_path]:
            os.chmod(f, 0o600)

        console.ok(f"Successfully initialized keys in {out_dir}:")
        console.msg(f"  - {cert_path}")
        console.msg(f"  - {key_path}")
        console.msg(f"  - {pem_path}")
        
        return True