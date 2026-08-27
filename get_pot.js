const { generate } = require('youtube-po-token-generator');

async function run() {
    try {
        const data = await generate();
        process.stdout.write(JSON.stringify(data));
        process.exit(0);
    } catch (err) {
        process.stderr.write(JSON.stringify({ error: err.message }));
        process.exit(1);
    }
}

run();
