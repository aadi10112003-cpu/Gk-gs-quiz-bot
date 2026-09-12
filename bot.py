import os, json, base64, asyncio, logging
from pathlib import Path
import requests
from openai import OpenAI

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

client = OpenAI(api_key=OPENAI_API_KEY)
TG = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

MASTER_PROMPT = Path("prompt.txt").read_text(encoding="utf-8")

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 4, "maxItems": 4
                    },
                    "correct_index": {"type": "integer", "minimum": 0, "maximum": 3},
                    "telegram_explanation": {"type": "string"},
                    "detailed_explanation": {"type": "string"}
                },
                "required": ["question","options","correct_index",
                              "telegram_explanation","detailed_explanation"],
                "additionalProperties": False
            }
        }
    },
    "required": ["title","questions"],
    "additionalProperties": False
}

def tg(method, **kwargs):
    r = requests.post(f"{TG}/{method}", data=kwargs, timeout=60)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data)
    return data["result"]

def download_telegram_file(file_id):
    f = tg("getFile", file_id=file_id)
    url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{f['file_path']}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content

def make_quiz(image_bytes):
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = "data:image/jpeg;base64," + b64

    instructions = MASTER_PROMPT + """

TELEGRAM OUTPUT RULES:
- Return JSON only, matching the supplied schema.
- Generate every meaningful source-page question supported by the readable page.
- Exactly 4 options per question and exactly one correct option.
- correct_index is zero-based.
- telegram_explanation MUST be <= 200 characters because Telegram's native quiz explanation limit is 200 characters.
- telegram_explanation should give the key learning point, not just say correct/incorrect.
- detailed_explanation should be a stronger teaching explanation in Hinglish/Hindi+English.
- Do NOT put the answer in the question text.
- Uploaded page is the source of truth for source-page questions/answers.
- For explanation quality, verify against reliable educational sources when appropriate, but do not add external facts to the source-page quiz.
"""

    response = client.responses.create(
        model=MODEL,
        instructions=instructions,
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text",
                 "text": "Analyze this uploaded book page and create the Telegram quiz."},
                {"type": "input_image", "image_url": data_url}
            ]
        }],
        text={
            "format": {
                "type": "json_schema",
                "name": "telegram_quiz",
                "strict": True,
                "schema": SCHEMA
            }
        }
    )
    return json.loads(response.output_text)

def send_quiz(chat_id, quiz):
    # Native Telegram quiz polls. Shuffle options is disabled so the
    # generated correct_index remains stable.
    sent = []
    for i, q in enumerate(quiz["questions"], start=1):
        question = f"{i}. {q['question']}"
        result = tg(
            "sendPoll",
            chat_id=chat_id,
            question=question[:300],
            options=json.dumps([{"text": x[:100]} for x in q["options"]], ensure_ascii=False),
            is_anonymous="false",
            type="quiz",
            allows_multiple_answers="false",
            correct_option_ids=json.dumps([q["correct_index"]]),
            explanation=q["telegram_explanation"][:200],
            shuffle_options="false",
        )
        sent.append((result["poll"]["id"], q["detailed_explanation"]))
    return sent

def main():
    offset = 0
    print("Bot running...")
    while True:
        try:
            updates = tg(
                "getUpdates",
                timeout=30,
                offset=offset,
                allowed_updates=json.dumps(["message", "poll_answer"])
            )
            for u in updates:
                offset = u["update_id"] + 1

                msg = u.get("message")
                if msg and msg.get("photo"):
                    chat_id = msg["chat"]["id"]
                    tg("sendMessage", chat_id=chat_id,
                       text="📚 Page received. Quiz bana raha hoon…")

                    try:
                        photo = msg["photo"][-1]
                        image = download_telegram_file(photo["file_id"])
                        quiz = make_quiz(image)

                        # Store explanations in memory for this running process.
                        # Keyed by poll id after sending.
                        sent = send_quiz(chat_id, quiz)
                        for poll_id, explanation in sent:
                            EXPLANATIONS[poll_id] = (chat_id, explanation)

                        tg("sendMessage", chat_id=chat_id,
                           text=f"✅ {len(sent)}-question interactive quiz Telegram par bhej di.")
                    except Exception as e:
                        logging.exception("Quiz generation failed")
                        tg("sendMessage", chat_id=chat_id,
                           text="❌ Quiz banate waqt error aaya. Logs check karo.")

                pa = u.get("poll_answer")
                if pa:
                    poll_id = pa["poll_id"]
                    item = EXPLANATIONS.get(poll_id)
                    if item:
                        chat_id, explanation = item
                        # In a group, this posts the detailed teaching explanation.
                        # For a private chat, it appears directly to the learner.
                        tg("sendMessage", chat_id=chat_id,
                           text="🧠 Explanation:\n\n" + explanation[:3900])

        except Exception:
            logging.exception("Polling loop error")
            time.sleep(3)

if __name__ == "__main__":
    EXPLANATIONS = {}
    import time
    main()
