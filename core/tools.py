import aiohttp


class Tools:

    @staticmethod
    async def search(query):

        url = f"https://ddg-api.deno.dev/search?q={query}&limit=3"

        async with aiohttp.ClientSession() as session:

            async with session.get(url) as r:

                if r.status != 200:
                    return None

                data = await r.json()

                text = ""

                for d in data:
                    text += d["title"] + "\n"
                    text += d["snippet"] + "\n\n"

                return text
