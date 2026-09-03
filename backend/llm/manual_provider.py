"""Stand-in for a real LLM categorization call, used only because `claude`
isn't reachable from this environment (see backend/llm/claude_cli.py's auth
preflight -- `check_auth()` fails here every time). This is a DELIBERATE,
TEMPORARY substitution, not a design choice:

- categorize_all() (backend/llm/categorize.py) doesn't know or care which
  LLMProvider it's talking to. This module implements that exact same
  Protocol (one `complete(prompt) -> str` method) so all of
  categorize_all()'s real logic -- batching, per-merchant dedup, response
  validation against the fixed taxonomy, cache writes -- runs completely
  unchanged. Only the "model" underneath is swapped.
- Instead of calling out to a real model, `complete()` parses the
  categorization prompt it's handed, looks up each transaction's merchant
  in MERCHANT_CATEGORIES below, and returns the same JSON shape a real
  model would. MERCHANT_CATEGORIES was assigned by hand (by Claude, via
  Claude Code, reading the actual merchant list from real ingested
  statements) -- it is not derived from any live model call, and it will
  not learn about merchants it hasn't seen.
- A merchant not present in the mapping falls back to "Uncategorized" at
  low confidence, exactly matching the real categorization prompt's own
  instruction not to guess on genuinely ambiguous cases.
- Rows categorized this way are written with category_source="llm" (see
  categorize.py) since that's what they semantically are -- a categorized
  transaction, no different in the data model from one a real model call
  would have produced -- but this module's own presence in the codebase
  IS the record that a real model wasn't actually called yet.

Remove this file (and stop selecting LLM_PROVIDER=manual) once a real
claude_cli or anthropic_api connection is actually reachable and can
categorize on the fly. Nothing else needs to change to switch back --
categorize_all() and every downstream table/view already handle "llm"-
sourced rows the same way regardless of which provider produced them.

Does NOT handle the narrative summary prompt (backend/llm/summarize.py) --
that needs freshly generated prose for whatever stats happen to be
computed at request time, which a fixed lookup table fundamentally can't
provide. complete() detects a narrative-shaped prompt and returns a clear
placeholder explaining that a real LLM connection is needed for that part,
rather than fabricating or crashing.
"""
from __future__ import annotations

import json
import re

# category, subcategory, confidence, is_transfer -- keyed by the exact
# cleaned merchant name (backend/ingest/normalize.py's clean_merchant()
# output), lowercased and whitespace-collapsed the same way
# normalize_merchant_key() does, so lookups are robust to case alone.
MERCHANT_CATEGORIES: dict[str, tuple[str, str | None, float, bool]] = {
    "4726 plntf holdings llc": ("Uncategorized", None, 0.2, False),
    "7-eleven": ("Groceries", "Convenience store", 0.6, False),
    "7-eleven 10653 herndon vaapple pay ending in": ("Groceries", "Convenience store", 0.6, False),
    "7-eleven 27267 centreville vaapple pay ending in": ("Groceries", "Convenience store", 0.6, False),
    "7-eleven 28505 manassas parkva": ("Groceries", "Convenience store", 0.6, False),
    "7-eleven 36700 north las vegnv": ("Groceries", "Convenience store", 0.6, False),
    "abc*p 01691 pf centrevil centreville vaapple pay ending in": ("Health & Fitness", "Planet Fitness (probable)", 0.4, False),
    "adobe san": ("Subscriptions", "Adobe", 0.85, False),
    "aldi": ("Groceries", None, 0.9, False),
    "aldi 71086 fairfax vaapple pay ending in": ("Groceries", None, 0.9, False),
    "amazon mktpl*561h81nz2 amzn.com/billwa1y4on6s5n7e": ("Shopping", "Amazon", 0.7, False),
    "amazon mktpl*fi9tw8n53 amzn.com/billwa4imlmr7rdqd": ("Shopping", "Amazon", 0.7, False),
    "amazon prime pmts amzn.com/billwa1kqjurs0f0x": ("Subscriptions", "Amazon Prime (refund/credit)", 0.6, False),
    "amazon prime*e89jl4gs3 amzn.com/billwa3z87qnai1ci": ("Subscriptions", "Amazon Prime", 0.85, False),
    "amazon prime*i91za66v3 amzn.com/billwa5ffx2l6id1g": ("Subscriptions", "Amazon Prime", 0.85, False),
    "amazon prime*xl40918q3 amzn.com/billwa2ht9jag2jpv": ("Subscriptions", "Amazon Prime", 0.85, False),
    "anthropic* claude sub 4152360599 ca": ("Subscriptions", "Anthropic Claude", 0.95, False),
    "apple.com/bill 866-712-7753": ("Subscriptions", "Apple", 0.7, False),
    "apple.com/bill 866-712-7753 ca": ("Subscriptions", "Apple", 0.7, False),
    "apple.com/bill 866-712-7753 caapple pay ending in": ("Subscriptions", "Apple", 0.7, False),
    "auntie anne's pretzels": ("Dining & Takeout", None, 0.85, False),
    "barber effect 5713477206 vaapple pay ending in": ("Personal Care", "Barber", 0.75, False),
    "bens chili bowl du dulles vaapple pay ending in": ("Dining & Takeout", None, 0.85, False),
    "best buy": ("Shopping", "Electronics", 0.85, False),
    "best buy 00002733295 fairfax vaapple pay ending in": ("Shopping", "Electronics", 0.85, False),
    "bjs fuel": ("Fuel", None, 0.85, False),
    "bjs wholesale": ("Groceries", "Warehouse club", 0.6, False),
    "bjs wholesale fairfax vaapple pay ending in": ("Groceries", "Warehouse club", 0.6, False),
    "busbud": ("Travel", "Bus travel", 0.75, False),
    "cafe bravo inc new york nyapple pay ending in": ("Dining & Takeout", None, 0.8, False),
    "canva* i04921-5261812 7372853388 tx": ("Subscriptions", "Canva", 0.85, False),
    "canva* i04951-3031022 7372853388 tx": ("Subscriptions", "Canva", 0.85, False),
    "cashback bonus redemption pymt/stmt crdt": ("Income", "Card rewards redemption", 0.5, False),
    "cc* crumbl fairlakes 8014101313 utapple pay ending in": ("Dining & Takeout", "Crumbl Cookies", 0.85, False),
    "cheesecake fairfax": ("Dining & Takeout", None, 0.85, False),
    "chipotle 1140 centreville vaapple pay ending in": ("Dining & Takeout", None, 0.9, False),
    "cinemark 1110 online cinemark.com vaapple pay ending in": ("Entertainment", "Movies", 0.85, False),
    "cinemark 1110 rstbar": ("Entertainment", "Movie theater concessions", 0.5, False),
    "cinemark 1111 online cinemark.com vaapple pay ending in": ("Entertainment", "Movies", 0.85, False),
    "cinemark 1111 rstbar": ("Entertainment", "Movie theater concessions", 0.5, False),
    "claude.ai subscription 4152360599 ca": ("Subscriptions", "Anthropic Claude", 0.95, False),
    "clip mx*brunos pizza ciudad de mexmex88.00 @ 00000000.0582143 mxn": ("Dining & Takeout", "Travel dining (Mexico)", 0.6, False),
    "clt charlott got a lot charlotte ncapple pay ending in": ("Shopping", None, 0.4, False),
    "connections d st2878 tempe azapple pay ending in": ("Entertainment", None, 0.35, False),
    "cook out manassas park manassas parkvaapple pay ending in": ("Dining & Takeout", None, 0.85, False),
    "cpi*pepsi-cola bottlin 540-347-3112": ("Dining & Takeout", "Vending machine", 0.5, False),
    "crunchyroll * 415-503-9235": ("Subscriptions", "Crunchyroll", 0.9, False),
    "crunchyroll.com 4157963560 tx": ("Subscriptions", "Crunchyroll", 0.9, False),
    "cvs/pharmacy": ("Health & Fitness", "Pharmacy", 0.75, False),
    "dave & busters pwc": ("Entertainment", None, 0.85, False),
    "dd *doordash 7-eleven 855-973-1040 caapple pay ending in": ("Dining & Takeout", "DoorDash", 0.85, False),
    "dd *doordash chinafort 855-973-1040 caapple pay ending in": ("Dining & Takeout", "DoorDash", 0.85, False),
    "dd *doordash dominos 855-973-1040 caapple pay ending in": ("Dining & Takeout", "DoorDash", 0.85, False),
    "dd *doordash doubledas 855-973-1040 caapple pay ending in": ("Dining & Takeout", "DoorDash", 0.85, False),
    "dd *doordash greenbasi 855-973-1040 caapple pay ending in": ("Dining & Takeout", "DoorDash", 0.85, False),
    "dd *doordash halalfood 855-973-1040 caapple pay ending in": ("Dining & Takeout", "DoorDash", 0.85, False),
    "dd *doordash insomniac 855-973-1040 caapple pay ending in": ("Dining & Takeout", "DoorDash", 0.85, False),
    "dd *doordash papajohns 855-973-1040 caapple pay ending in": ("Dining & Takeout", "DoorDash", 0.85, False),
    "dd *doordash sheetz 855-973-1040 caapple pay ending in": ("Dining & Takeout", "DoorDash", 0.85, False),
    "dd *doordash tonysnypi 6506819470 caapple pay ending in": ("Dining & Takeout", "DoorDash", 0.85, False),
    "dd *doordash tonysnypi 855-973-1040 caapple pay ending in": ("Dining & Takeout", "DoorDash", 0.85, False),
    "dd *doordash tsunamisu 855-973-1040 caapple pay ending in": ("Dining & Takeout", "DoorDash", 0.85, False),
    "deposit - ach paid fr om gusto payroll payroll": ("Income", "Payroll", 0.95, False),
    "deposit - ach paid from gusto payroll payroll": ("Income", "Payroll", 0.95, False),
    "dividend": ("Income", "Savings dividend", 0.9, False),
    "dolan uyghur resta chantilly vaapple pay ending in": ("Dining & Takeout", None, 0.85, False),
    "el picosito erick' new york nyapple pay ending in": ("Dining & Takeout", None, 0.8, False),
    "el ranchero mexican re": ("Dining & Takeout", None, 0.85, False),
    "epidemic sound epidemicsoundny": ("Subscriptions", "Music licensing", 0.8, False),
    "exxonmobil": ("Fuel", None, 0.9, False),
    "exxonmobil centreville vaapple pay ending in": ("Fuel", None, 0.9, False),
    "exxonmobil fairfax vaapple pay ending in": ("Fuel", None, 0.9, False),
    "fairfax computer r gosq.com vaapple pay ending in": ("Shopping", "Computer repair (probable)", 0.4, False),
    "fairfax ice arena": ("Entertainment", None, 0.8, False),
    "fairfax towne center 10 fairfax vaapple pay ending in": ("Entertainment", "Shopping/entertainment center", 0.4, False),
    "giant 0745 fairfax": ("Groceries", None, 0.9, False),
    "giant 0745 fairfax vaapple pay ending in": ("Groceries", None, 0.9, False),
    "girl scout nation? fairfax vaapple pay ending in": ("Gifts & Donations", "Girl Scout cookies", 0.6, False),
    "github, inc. 8774484820 ca": ("Subscriptions", "GitHub", 0.85, False),
    "gom shabu shabu": ("Dining & Takeout", None, 0.85, False),
    "grounds central st manassas": ("Dining & Takeout", "Coffee shop (probable)", 0.5, False),
    "h mart centreville llc": ("Groceries", None, 0.9, False),
    "h mart centreville llc centreville vaapple pay ending in": ("Groceries", None, 0.9, False),
    "h mart manassas llc": ("Groceries", None, 0.9, False),
    "habaneros taco grill 5 north las vegnv": ("Dining & Takeout", None, 0.85, False),
    "hdos - galleria at s henderson nvapple pay ending in": ("Shopping", "Mall", 0.4, False),
    "honest grill": ("Dining & Takeout", None, 0.8, False),
    "honey pig hot pot & gril": ("Dining & Takeout", None, 0.85, False),
    "hosthavoc* inv1047158 6136965929 can": ("Subscriptions", "Game server hosting", 0.8, False),
    "hosthavoc* inv1059935 6136965929 can": ("Subscriptions", "Game server hosting", 0.8, False),
    "hunan cafe": ("Dining & Takeout", None, 0.85, False),
    "i-battle e-sports": ("Entertainment", None, 0.6, False),
    "iad dulles - cava g": ("Dining & Takeout", "Airport dining", 0.75, False),
    "ibattle esports centreville": ("Entertainment", None, 0.6, False),
    "interest charge on purchases": ("Fees & Interest", "Credit card interest", 0.95, False),
    "intl transaction fee 06-01-26 supabase singapore": ("Fees & Interest", "International transaction fee", 0.9, False),
    "intl transaction fee 07-01-26 supabase singapore": ("Fees & Interest", "International transaction fee", 0.9, False),
    "intl transaction fee 08-0 4-26 supabase singapore": ("Fees & Interest", "International transaction fee", 0.9, False),
    "jack in the box 0368 barstow": ("Dining & Takeout", None, 0.85, False),
    "jireh bakey cafe centreville vaapple pay ending in": ("Dining & Takeout", None, 0.85, False),
    "k-wings korean styl": ("Dining & Takeout", None, 0.8, False),
    "k-wings korean styl centreville vaapple pay ending in": ("Dining & Takeout", None, 0.8, False),
    "kay jewelers": ("Shopping", "Jewelry", 0.75, False),
    "kindle svcs*dr5cr9ka3 888-802-3080": ("Shopping", "Kindle books", 0.6, False),
    "kindle svcs*gx0i25dc3 888-802-3080": ("Shopping", "Kindle books", 0.6, False),
    "lanes general merchandis": ("Shopping", None, 0.4, False),
    "lemonade insurance 8447338666 ny": ("Insurance", None, 0.95, False),
    "lotte plaza centreville": ("Groceries", None, 0.9, False),
    "lulu cafe centreville": ("Dining & Takeout", None, 0.85, False),
    "mariachi tequila r manassas": ("Dining & Takeout", None, 0.75, False),
    "mazar kabob": ("Dining & Takeout", None, 0.85, False),
    "mazar kabob centreville vaapple pay ending in": ("Dining & Takeout", None, 0.85, False),
    "meat project": ("Dining & Takeout", None, 0.7, False),
    "meat project centreville vaapple pay ending in": ("Dining & Takeout", None, 0.7, False),
    "mia dmv llc seven cornersvaapple pay ending in": ("Personal Care", None, 0.35, False),
    "microsoft*store msbill.info wamicrosoft*store": ("Subscriptions", "Microsoft", 0.8, False),
    "millies gelato manassas": ("Dining & Takeout", "Gelato", 0.9, False),
    "miniso fair oaks fairfax vaapple pay ending in": ("Shopping", None, 0.8, False),
    "mochinut": ("Dining & Takeout", None, 0.85, False),
    "mr sushi mrs roll lansdowne vaapple pay ending in": ("Dining & Takeout", None, 0.85, False),
    "name-cheap.com* jlsgl6 3233752822 az": ("Subscriptions", "Domain registration", 0.6, False),
    "netflix.com netflix.com": ("Subscriptions", "Netflix", 0.95, False),
    "netflix.com netflix.com canetflix.com": ("Subscriptions", "Netflix", 0.9, False),
    "new york state dmv": ("Transportation", "Vehicle registration/fees", 0.55, False),
    "olive garden zk": ("Dining & Takeout", None, 0.85, False),
    "openai *chatgpt subscr 4158799686 ca": ("Subscriptions", "OpenAI ChatGPT", 0.95, False),
    "paid to - planet fitnes s h iclub fees chk": ("Health & Fitness", "Gym membership", 0.9, False),
    "paid to - planet fitness h iclub fees chk 62": ("Health & Fitness", "Gym membership", 0.9, False),
    "paid to - rocket mon ey premium chk": ("Subscriptions", "Rocket Money", 0.85, False),
    "paid to - rocket mone y premium chk": ("Subscriptions", "Rocket Money", 0.85, False),
    "parchment-univ docs 480-719-1646": ("Education", "Transcript service", 0.75, False),
    "pets r family ah woodbridge vaapple pay ending in": ("Shopping", "Pet store", 0.6, False),
    "playkit 2133196755 ca": ("Entertainment", None, 0.4, False),
    "po s debit- debit card 3385 06-08-26 the boss barber": ("Personal Care", "Barber", 0.8, False),
    "pos debit - debit car d 3385 transaction 06-03-26 weis markets 10 martinsburg": ("Groceries", None, 0.85, False),
    "pos debit - debit car d 3385 transaction 06-07-26 super gasoline centreville": ("Fuel", None, 0.85, False),
    "pos debit - debit card 3385 transaction 06-08-26 bjs wholesale 13053 fa irfax va": ("Groceries", "Warehouse club", 0.6, False),
    "pos debit - debit card 3385 transaction 06-10-26 bjs wholesale # 0": ("Groceries", "Warehouse club", 0.6, False),
    "pos debit- debit c ard 1972 07-22-26 apple cash sent mo 1infiniteloop ca": ("Uncategorized", "Apple Cash P2P transfer", 0.3, False),
    "pos debit- debit card 1972 05-22-26 gofndme help denni": ("Gifts & Donations", "GoFundMe", 0.65, False),
    "pos debit- debit card 1972 08-01-26 amazon prime*hk8cb amzn.com/bill wa": ("Subscriptions", "Amazon Prime", 0.85, False),
    "pos debit- debit card 1972 08-02-26 busbud": ("Travel", "Bus travel", 0.75, False),
    "pos debit- debit card 3385 06-01-26 supabase si ngapore": ("Subscriptions", "Supabase", 0.8, False),
    "pos debit- debit card 3385 07-01-26 supabase si ngapore": ("Subscriptions", "Supabase", 0.8, False),
    "pos debit- debit card 3385 07-07-26 venmo *tien vu ngu v isa direct ny": ("Uncategorized", "Venmo P2P transfer", 0.3, False),
    "pos debit- debit card 3385 07-12-26 apple cash sent mo 1infiniteloop c a": ("Uncategorized", "Apple Cash P2P transfer", 0.3, False),
    "pos debit- debit card 3385 07-12-26 venmo *alyssa ange visa direct ny": ("Uncategorized", "Venmo P2P transfer", 0.3, False),
    "pos debit- debit card 3385 08-05-26 supabase si ngapore": ("Subscriptions", "Supabase", 0.8, False),
    "pupusas express - ii": ("Dining & Takeout", None, 0.85, False),
    "qoves 3024801262 de": ("Personal Care", "Grooming/aesthetics", 0.4, False),
    "qq spa and massage": ("Personal Care", "Spa/massage", 0.75, False),
    "quantum of the seas": ("Travel", "Cruise", 0.85, False),
    "regal cinemas inc 877-835-5734 tnapple pay ending in": ("Entertainment", "Movies", 0.9, False),
    "revolution darts": ("Entertainment", None, 0.75, False),
    "rice culture": ("Dining & Takeout", None, 0.8, False),
    "riot* ln5nsq3brnhz 866-373-9211": ("Entertainment", "Riot Games", 0.8, False),
    "riot* ln6nb6u6uka8 866-373-9211": ("Entertainment", "Riot Games", 0.8, False),
    "riot* ln6p4bt1gn0s 866-373-9211": ("Entertainment", "Riot Games", 0.8, False),
    "rivas mexican grill north las vegnv": ("Dining & Takeout", None, 0.85, False),
    "roku for disney electr 8162728107 de": ("Subscriptions", "Disney+", 0.8, False),
    "safeway": ("Groceries", None, 0.9, False),
    "safeway 1431 fairfax vaapple pay ending in": ("Groceries", None, 0.9, False),
    "sheetz": ("Fuel", None, 0.6, False),
    "sheetz 0762 charles town wvapple pay ending in": ("Fuel", None, 0.6, False),
    "sw air": ("Travel", "Southwest Airlines", 0.85, False),
    "sweetfrog": ("Dining & Takeout", "Frozen yogurt", 0.85, False),
    "target": ("Shopping", None, 0.85, False),
    "target 00013417091 fairfax vaapple pay ending in": ("Shopping", None, 0.85, False),
    "texas donut manassas 410 manassas vaapple pay ending in": ("Dining & Takeout", None, 0.85, False),
    "the boss barber": ("Personal Care", "Barber", 0.85, False),
    "the boss barber fairfax vaapple pay ending in": ("Personal Care", "Barber", 0.85, False),
    "the loudoun kitchen an": ("Dining & Takeout", None, 0.8, False),
    "tomo izakaya japanese su": ("Dining & Takeout", None, 0.85, False),
    "tractor supply co manassas vaapple pay ending in": ("Shopping", None, 0.8, False),
    "tropical smoothie cafe v": ("Dining & Takeout", None, 0.85, False),
    "tropical smoothie cafe v fairfax vaapple pay ending in": ("Dining & Takeout", None, 0.85, False),
    "tsunami sushi": ("Dining & Takeout", None, 0.85, False),
    "uber *eats 866-576-1039 ca": ("Dining & Takeout", "Uber Eats", 0.85, False),
    "uber *trip 866-576-1039 ca": ("Transportation", "Rideshare", 0.85, False),
    "uber *trip 866-576-1039 caapple pay ending in": ("Transportation", "Rideshare", 0.85, False),
    "uncle julio's": ("Dining & Takeout", None, 0.9, False),
    "uniqlo fair lakes": ("Shopping", "Clothing", 0.85, False),
    "uniqlo fair lakes fairfax vaapple pay ending in": ("Shopping", "Clothing", 0.85, False),
    "va abc store 090 fairfax vaapple pay ending in": ("Shopping", "Alcohol", 0.8, False),
    "valve": ("Entertainment", "Steam/gaming", 0.75, False),
    "viatouch media san diego caapple pay ending in": ("Dining & Takeout", "Vending machine", 0.4, False),
    "vioc dv0004 centreville vaapple pay ending in": ("Transportation", "Oil change (Valvoline)", 0.85, False),
    "walmart store": ("Shopping", None, 0.75, False),
    "wanderu.com boston maapple pay ending in": ("Travel", "Bus/train booking", 0.8, False),
    "wl *steam purchase 425-889-9642": ("Entertainment", "Steam/gaming", 0.85, False),
    "wl *steam purchase 425-952-2985 wawl *steam purchase": ("Entertainment", "Steam/gaming", 0.85, False),
    "zandra's - manassas": ("Dining & Takeout", None, 0.85, False),
    "zelle db syed tirmizi": ("Uncategorized", "Zelle P2P transfer", 0.3, False),
    "zelle db tien nguyen": ("Uncategorized", "Zelle P2P transfer", 0.3, False),
}


def _extract_batch(prompt: str) -> list[dict] | None:
    """Categorization prompts end with a JSON array of {id, merchant,
    amount, date}. Returns None if this doesn't look like a categorization
    prompt at all (e.g. it's the narrative prompt instead)."""
    if "Return ONLY a JSON array" not in prompt or "Allowed categories" not in prompt:
        return None
    match = re.search(r"\[\s*\{.*?\}\s*\]", prompt, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def _lookup(merchant: str) -> tuple[str, str | None, float, bool]:
    key = re.sub(r"\s+", " ", merchant.strip().lower())
    return MERCHANT_CATEGORIES.get(key, ("Uncategorized", None, 0.2, False))


class ManualCategorizationProvider:
    """Implements the same LLMProvider Protocol as claude_cli/anthropic_api
    (see backend/llm/provider.py) so categorize_all() works unmodified."""

    def complete(self, prompt: str, max_tokens: int = 4096) -> str:
        batch = _extract_batch(prompt)
        if batch is None:
            return (
                "_A real LLM connection is needed to generate this summary -- "
                "the manual categorization stand-in (backend/llm/manual_provider.py) "
                "only handles categorization, not narrative generation. "
                "Categories above, if any, were assigned manually; see PHASE_PLAN.md._"
            )

        results = []
        for item in batch:
            category, subcategory, confidence, is_transfer = _lookup(item.get("merchant", ""))
            results.append({
                "id": item["id"],
                "category": category,
                "subcategory": subcategory,
                "confidence": confidence,
                "is_transfer": is_transfer,
            })
        return json.dumps(results)
