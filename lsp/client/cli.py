from lsp.client import Client
import asyncio
import click


async def amain(lsp: str) -> None:
    async with Client().run([lsp]):
        await asyncio.sleep(0.1)


@click.command
@click.argument('lsp')
def main(lsp: str) -> None:
    asyncio.run(amain(lsp))
