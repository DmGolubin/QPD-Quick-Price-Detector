// Visual selector JS
async function loadPage() {
    const url = document.getElementById('target-url').value;
    if (!url) return;
    const resp = await fetch('/selector/proxy', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url})
    });
    const data = await resp.json();
    if (data.error) {
        alert('Ошибка: ' + data.error);
        return;
    }
    const frame = document.getElementById('preview-frame');
    frame.srcdoc = data.html;
}

window.addEventListener('message', function(e) {
    if (e.data && e.data.type === 'element_selected') {
        document.getElementById('selector-panel').style.display = 'block';
        document.getElementById('css-result').value = e.data.css || '';
        document.getElementById('xpath-result').value = e.data.xpath || '';
        document.getElementById('text-result').value = e.data.text || '';
    }
});

function expandSelection() {
    const frame = document.getElementById('preview-frame');
    frame.contentWindow.postMessage({type: 'expand'}, '*');
}

function narrowSelection() {
    const frame = document.getElementById('preview-frame');
    frame.contentWindow.postMessage({type: 'narrow'}, '*');
}

function confirmSelection() {
    const css = document.getElementById('css-result').value;
    if (css) {
        alert('Селектор скопирован: ' + css);
        navigator.clipboard.writeText(css);
    }
}
