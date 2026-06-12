import asyncio
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        # Send a Medical SOS using natural language (NO commas, so OpenAI parses it)
        req1 = client.post("http://localhost:8000/api/twilio/inbound", data={
            "From": "+919999999901",
            "Body": "My mother is having a severe heart attack and we are trapped by flood waters! We urgently need a medical airlift at 27.23, 94.10."
        })
        
        # Send a Rescue SOS using natural language (NO commas, so OpenAI parses it)
        req2 = client.post("http://localhost:8000/api/twilio/inbound", data={
            "From": "+919999999902",
            "Body": "Help! Five people are trapped on a sinking roof and the water is rising fast. We need an immediate helicopter rescue at 27.23, 94.10."
        })
        
        # Fire both at the EXACT SAME MILLISECOND to guarantee a resource conflict
        print("Firing two simultaneous emergencies...")
        results = await asyncio.gather(req1, req2)
        print("Fired! Check your Conflict Dashboard in a few seconds.")

if __name__ == "__main__":
    asyncio.run(main())
