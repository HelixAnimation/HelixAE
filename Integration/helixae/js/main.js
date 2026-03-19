const csInterface = new CSInterface();
(function () {
    'use strict';
    const net = require('net');

    const server = net.createServer((socket) => {
        socket.on('data', (data) => {
            data = String(data);
            if (data === "pid") {
                socket.write(`${process.pid}`);
                return;
            } else {
                csInterface.evalScript(data, (result) => {
                    socket.write(result === "" ? "null" : result);
                });
            }
        });
    });

    server.maxConnections = 2;
    server.listen(9888, () => {
        console.log('Helix AE Server listening on port 9888');
    });

    setTimeout(setupButtons, 300);
    setTimeout(launchHelixAE, 500);
}());

function setupButtons() {
    let object = {
        'Save Version': 'saveVersion',
        'Save Comment...': 'saveExtended',
        'Project Browser...': 'projectBrowser',
        'Footage Tracker...': 'footageTracker',
        'Import Media...': 'importMedia',
        'Check for New Versions...': 'checkVersions',
        'Helix Settings...': 'settings',
        'Render...': 'render',
    };
    const w_buttons = document.getElementById("w_buttons");
    for (const [key, value] of Object.entries(object)) {
        const thisButton = document.createElement("BUTTON");
        thisButton.innerHTML = key;
        thisButton.setAttribute("class", "scriptButton");
        thisButton.setAttribute("onclick", `onButtonClick('${value}')`);
        w_buttons.appendChild(thisButton);
    };
}

function launchHelixAE() {
    onButtonClick('launch');
}

function onButtonClick(cmd) {
    const path = require('path');
    const cmdFilePath = path.join(__dirname, '..', 'helixae.cmd');

    console.log(`Executing command: "${cmdFilePath}"`);

    startProcess(cmdFilePath, cmd);
}

function startProcess(cmdFilePath, cmd) {
    const { spawn } = require('child_process');

    const isWin = process.platform === 'win32';

    if (isWin) {
        const child = spawn(cmdFilePath, [cmd], { shell: false });
    } else {
        const child = spawn("\"%s\"" % cmdFilePath, [cmd], { shell: true }); // for mac
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

    return child;
}

function showErrorMessage(message) {
    var escapedMessage = message.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\r/g, '\\r');
    csInterface.evalScript(`alert("${escapedMessage}")`);
}
