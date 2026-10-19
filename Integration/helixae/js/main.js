const csInterface = new CSInterface();

// Commands the panel is allowed to request. Values are validated before
// anything is spawned; labels are used for the button text.
const HELIX_COMMANDS = {
    'Save Version': 'saveVersion',
    'Save Comment...': 'saveExtended',
    'Project Browser...': 'projectBrowser',
    'Footage Tracker...': 'footageTracker',
    'Import Media...': 'importMedia',
    'Check Issues': 'checkIssues',
    'Prism Settings...': 'settings',
    'Render...': 'render'
};

const BRIDGE_HOST = '127.0.0.1';
const BRIDGE_PORT = 9888;
const FRAME_END = 0x00;                    // request frame terminator (byte value)
const MAX_FRAME = 8 * 1024 * 1024;         // max request size in bytes
const REQUEST_IDLE_TIMEOUT = 120000;       // ms to wait for a complete frame

(function () {
    'use strict';
    const net = require('net');

    const server = net.createServer((socket) => {
        let buffer = Buffer.alloc(0);

        socket.on('error', (err) => {
            console.error('Socket error:', err.message);
        });

        // Destroy connections that never deliver a complete request frame.
        socket.setTimeout(REQUEST_IDLE_TIMEOUT);
        socket.on('timeout', () => {
            console.error('Bridge request timed out (incomplete frame).');
            socket.destroy();
        });

        socket.on('data', (data) => {
            buffer = Buffer.concat([buffer, data]);
            if (buffer.length > MAX_FRAME) {
                console.error('Bridge request exceeds maximum frame size.');
                socket.destroy();
                return;
            }

            const end = buffer.indexOf(FRAME_END);
            if (end === -1) {
                return; // accumulate bytes until the frame terminator arrives
            }

            // Decode the complete frame once; partial UTF-8 sequences stay intact.
            const request = buffer.slice(0, end).toString('utf-8');
            buffer = buffer.slice(end + 1);
            socket.setTimeout(0); // evaluation may legitimately take a long time

            if (!request) {
                console.error('Bridge received an empty request frame.');
                socket.destroy();
                return;
            }

            if (request === 'pid') {
                socket.write(process.pid + '\x00');
                return;
            }

            csInterface.evalScript(request, (result) => {
                if (!socket.destroyed) {
                    socket.write((result === '' ? 'null' : result) + '\x00');
                }
            });
        });
    });

    server.maxConnections = 64;

    server.on('error', (err) => {
        // Most commonly EADDRINUSE: another AE instance owns the bridge.
        // Never send panel commands to that instance from this one.
        const message = 'HelixAE bridge could not start on ' + BRIDGE_HOST + ':' +
            BRIDGE_PORT + '. Another After Effects instance is probably using it.\n' +
            '(' + err.message + ')';
        console.error(message);
        disablePanel(message);
    });

    server.listen(BRIDGE_PORT, BRIDGE_HOST, () => {
        console.log('Helix AE bridge listening on ' + BRIDGE_HOST + ':' + BRIDGE_PORT);
        setupButtons();
        launchHelixAE();
    });
}());

function setupButtons() {
    const w_buttons = document.getElementById('w_buttons');
    for (const [label, value] of Object.entries(HELIX_COMMANDS)) {
        const thisButton = document.createElement('BUTTON');
        thisButton.innerHTML = label;
        thisButton.setAttribute('class', 'scriptButton');
        thisButton.setAttribute('onclick', `onButtonClick('${value}')`);
        w_buttons.appendChild(thisButton);
    };
}

function launchHelixAE() {
    onButtonClick('launch');
}

function onButtonClick(cmd) {
    const path = require('path');

    const allowed = Object.keys(HELIX_COMMANDS).map((key) => HELIX_COMMANDS[key]);
    if (allowed.indexOf(cmd) === -1 && cmd !== 'launch') {
        showErrorMessage(`Unknown HelixAE command: ${cmd}`);
        return;
    }

    const cmdFilePath = path.join(__dirname, '..', 'helixae.cmd');
    console.log(`Executing command: "${cmdFilePath}" ${cmd}`);
    startProcess(cmdFilePath, cmd);
}

function startProcess(cmdFilePath, cmd) {
    const { spawn } = require('child_process');

    let child;

    if (process.platform === 'win32') {
        // Spawn the .cmd through cmd.exe. The outer extra pair of quotes is
        // deliberate: with /s /c, cmd.exe strips the first and last quote,
        // leaving `"<path with spaces>" <cmd>` with the path still quoted.
        child = spawn(
            'cmd.exe',
            ['/d', '/s', '/c', '""' + cmdFilePath + '" ' + cmd + '"'],
            { windowsVerbatimArguments: true, windowsHide: true }
        );
    } else {
        // No launcher exists for other platforms yet; surface the failure.
        child = spawn(cmdFilePath, [cmd]);
    }

    child.stdout.on('data', (data) => {
        console.log(`stdout: ${data}`);
    });

    child.stderr.on('data', (data) => {
        console.error(`stderr: ${data}`);
    });

    child.on('error', (error) => {
        console.error(`Error executing command: ${error}`);
        showErrorMessage(`Error executing command: ${error.message}`);
    });

    child.on('exit', (code) => {
        if (code !== 0) {
            showErrorMessage(
                `HelixAE command "${cmd}" failed with exit code ${code}.\n` +
                'See the Prism logs for details.'
            );
        }
    });

    return child;
}

function setPanelStatus(message) {
    let status = document.getElementById('helixae_status');
    if (!status) {
        status = document.createElement('div');
        status.id = 'helixae_status';
        const container = document.getElementById('w_buttons');
        if (container && container.parentNode) {
            container.parentNode.insertBefore(status, container);
        } else {
            document.body.appendChild(status);
        }
    }
    status.innerHTML = message;
}

function disablePanel(message) {
    const container = document.getElementById('w_buttons');
    if (container) {
        for (const button of container.getElementsByTagName('button')) {
            button.disabled = true;
        }
    }
    setPanelStatus('<b>' + message.replace(/</g, '&lt;') + '</b>');
    showErrorMessage(message);
}

function showErrorMessage(message) {
    var escapedMessage = message.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r');
    csInterface.evalScript(`alert("${escapedMessage}")`);
}
