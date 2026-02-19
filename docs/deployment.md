# Deployment And Operations (Old Mac)

## Deploy Update

```bash
cd ~/apps/translatorBot
source .venv/bin/activate
git pull
pip install -r requirements.txt
```

## Restart Bot Process

```bash
cd ~/apps/translatorBot
pkill -f ' -m bot.main' || true
nohup .venv/bin/python -m bot.main >/dev/null 2>&1 < /dev/null &
```

## Verify Running Process

```bash
ps aux | grep '[b]ot.main'
```

## Run Tests

```bash
cd ~/apps/translatorBot
source .venv/bin/activate
pytest -q
```

## Check Logs

```bash
cd ~/apps/translatorBot
tail -n 100 logs/bot.log
```

## Security Notes

- Never print or paste real tokens into logs.
- Keep `.env` only on runtime host.
- Rotate keys immediately if exposed.
