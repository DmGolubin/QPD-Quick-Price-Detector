// Macro builder JS
let steps = [];

function addStep() {
    const id = steps.length;
    steps.push({action_type: 'click', selector: '', params: {}});
    renderSteps();
}

function removeStep(idx) {
    steps.splice(idx, 1);
    renderSteps();
}

function renderSteps() {
    const container = document.getElementById('macro-steps');
    container.innerHTML = steps.map((s, i) => `
        <div class="macro-step" draggable="true" data-idx="${i}">
            <span class="step-num">${i + 1}</span>
            <select onchange="steps[${i}].action_type=this.value" class="input input-sm">
                <option value="click" ${s.action_type === 'click' ? 'selected' : ''}>Click</option>
                <option value="type" ${s.action_type === 'type' ? 'selected' : ''}>Type</option>
                <option value="scroll" ${s.action_type === 'scroll' ? 'selected' : ''}>Scroll</option>
                <option value="wait" ${s.action_type === 'wait' ? 'selected' : ''}>Wait</option>
                <option value="select_option" ${s.action_type === 'select_option' ? 'selected' : ''}>Select</option>
                <option value="press_key" ${s.action_type === 'press_key' ? 'selected' : ''}>Press Key</option>
            </select>
            <input type="text" placeholder="Селектор" value="${s.selector || ''}"
                   onchange="steps[${i}].selector=this.value" class="input input-sm">
            <button onclick="removeStep(${i})" class="btn btn-sm btn-danger">🗑</button>
        </div>
    `).join('');
}

async function saveMacro() {
    const monitorId = new URLSearchParams(window.location.search).get('monitor_id');
    if (!monitorId) { alert('Укажите monitor_id в URL'); return; }
    // Save via API
    alert('Макрос сохранён (TODO: API integration)');
}
