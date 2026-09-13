// Expense Tracker Interactive Handlers

document.addEventListener('DOMContentLoaded', () => {
  // Preset Chips
  const presetChips = document.querySelectorAll('.preset-chip');
  const amountInput = document.getElementById('expense-amount-input');

  if (presetChips.length > 0 && amountInput) {
    presetChips.forEach(chip => {
      chip.addEventListener('click', () => {
        const val = chip.getAttribute('data-value');
        if (val) {
          amountInput.value = parseFloat(val).toFixed(2);
          amountInput.focus();
        }
      });
    });
  }

  // Client-side quick filter for transactions table if present
  const searchInput = document.getElementById('transaction-search-input');
  const tableRows = document.querySelectorAll('#ledger-tbody tr.ledger-row');

  if (searchInput && tableRows.length > 0) {
    searchInput.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase().trim();
      tableRows.forEach(row => {
        const text = row.innerText.toLowerCase();
        if (text.includes(q)) {
          row.style.display = '';
        } else {
          row.style.display = 'none';
        }
      });
    });
  }
});

// Modal helpers
function openDeleteModal(actionUrl, itemTitle) {
  const modal = document.getElementById('delete-modal');
  const form = document.getElementById('delete-modal-form');
  const titleElem = document.getElementById('delete-modal-title');
  if (modal && form) {
    form.setAttribute('action', actionUrl);
    const nextUrlInput = form.querySelector('input[name="next_url"]');
    if (nextUrlInput) nextUrlInput.value = window.location.pathname;
    if (titleElem && itemTitle) {
      titleElem.textContent = `Are you sure you want to delete "${itemTitle}"? This action cannot be undone.`;
    }
    modal.classList.remove('hidden');
    modal.classList.add('flex');
  }
}

function openClearAllModal(actionUrl) {
  const modal = document.getElementById('delete-modal');
  const form = document.getElementById('delete-modal-form');
  const titleElem = document.getElementById('delete-modal-title');
  if (modal && form) {
    form.setAttribute('action', actionUrl);
    const nextUrlInput = form.querySelector('input[name="next_url"]');
    if (nextUrlInput) nextUrlInput.value = window.location.pathname;
    if (titleElem) {
      titleElem.textContent = 'Are you sure you want to clear ALL expense records? This will purge your session ledger permanently.';
    }
    modal.classList.remove('hidden');
    modal.classList.add('flex');
  }
}

function closeDeleteModal() {
  const modal = document.getElementById('delete-modal');
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }
}

// Edit Modal helpers
function openEditModal(expenseId, currentAmount, currentDesc, currentCat) {
  const modal = document.getElementById('edit-modal');
  const form = document.getElementById('edit-modal-form');
  const amountField = document.getElementById('edit-amount-input');
  const descField = document.getElementById('edit-desc-input');
  const catField = document.getElementById('edit-category-input');

  if (modal && form) {
    form.setAttribute('action', `/expenses/${expenseId}/edit`);
    const nextUrlInput = form.querySelector('input[name="next_url"]');
    if (nextUrlInput) nextUrlInput.value = window.location.pathname;
    if (amountField) amountField.value = currentAmount;
    if (descField) descField.value = currentDesc;
    if (catField) catField.value = currentCat || 'General';
    modal.classList.remove('hidden');
    modal.classList.add('flex');
  }
}

function closeEditModal() {
  const modal = document.getElementById('edit-modal');
  if (modal) {
    modal.classList.add('hidden');
    modal.classList.remove('flex');
  }
}

// Mobile sidebar drawer toggle
function toggleMobileSidebar() {
  const sidebar = document.getElementById('main-sidebar');
  const backdrop = document.getElementById('mobile-sidebar-backdrop');
  if (!sidebar) return;
  const isClosed = sidebar.classList.contains('-translate-x-full');
  if (isClosed) {
    sidebar.classList.remove('-translate-x-full');
    if (backdrop) backdrop.classList.remove('hidden');
  } else {
    sidebar.classList.add('-translate-x-full');
    if (backdrop) backdrop.classList.add('hidden');
  }
}
