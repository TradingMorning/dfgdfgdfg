const http = require('http');
const { generate } = require('youtube-po-token-generator');

let cachedToken = null;
let lastGenerated = 0;

async function getFreshToken() {
    // Cache token for 45 minutes
    if (!cachedToken || (Date.now() - lastGenerated > 45 * 60 * 1000)) {
        console.log('[POT Server] Generating fresh BotGuard PO-Token...');
        cachedToken = await generate();
        lastGenerated = Date.now();
        console.log('[POT Server] Fresh PO-Token successfully generated.');
    }
    return cachedToken;
}

const server = http.createServer(async (req, res) => {
    if (req.url === '/token') {
        try {
            const data = await getFreshToken();
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(data));
        } catch (err) {
            console.error('[POT Server Error]', err);
            res.writeHead(500, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: err.message }));
        }
    } else {
        res.writeHead(404);
        res.end();
    }
});

// Warmup token immediately on startup
getFreshToken().catch(e => console.error('[POT Warmup Failed]', e.message));

server.listen(4444, '127.0.0.1', () => {
    console.log('[POT Server] Running on http://127.0.0.1:4444');
});
