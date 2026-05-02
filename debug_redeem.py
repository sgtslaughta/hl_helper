#!/usr/bin/env python3
"""Debug redeem to see what's happening."""
import asyncio
from pathlib import Path
import tempfile
from datetime import timedelta
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from server.app.crypto.ca import InternalCA
from server.app.crypto.signing import FileBackend
from server.app.enrollment.service import EnrollmentService
from server.app.models.base import Base


async def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Setup
        db_url = f'sqlite+aiosqlite:///{tmp_path / "test.db"}'
        engine = create_async_engine(db_url, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        sm = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        ca = InternalCA.bootstrap(tmp_path / 'ca')
        signing_backend = FileBackend.bootstrap(tmp_path / 'signing')
        service = EnrollmentService(
            ca=ca,
            signing_backend=signing_backend,
            grpc_endpoint='grpc://localhost:50051',
            cert_ttl=timedelta(hours=24),
        )

        # Create a token
        async with sm() as session:
            plaintext, _ = await service.issue_token(
                session, issued_by='admin@test', ttl=timedelta(minutes=15)
            )
            await session.commit()

        # Make CSR
        sk = ed25519.Ed25519PrivateKey.generate()
        pk_raw = sk.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
        csr = (
            x509.CertificateSigningRequestBuilder()
            .subject_name(x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, 'agent')]))
            .sign(sk, None)
        )
        csr_pem = csr.public_bytes(serialization.Encoding.PEM)

        # Try to redeem
        async with sm() as session:
            try:
                result = await service.redeem(
                    session,
                    token_plaintext=plaintext,
                    csr_pem=csr_pem,
                    hostname='test-host',
                    agent_pubkey=pk_raw,
                )
                await session.commit()
                print('SUCCESS')
            except Exception as e:
                import traceback
                print(f'ERROR: {type(e).__name__}: {e}')
                traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
