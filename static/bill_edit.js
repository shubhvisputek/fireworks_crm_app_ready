// Bill editing, "billed by" and "edited by" tracking.
// Loaded after ui_fixes.js; wraps the active billing and sales screens.

function fmtTime(value){
  if(!value)return '';
  const d=new Date(value);
  if(isNaN(d))return String(value);
  return d.toLocaleString('en-IN',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'});
}

function billHistory(x){
  const lines=[];
  if(x.revised_from_number){
    lines.push(`Edited by <strong>${esc(x.edited_by_name||'-')}</strong> on ${esc(fmtTime(x.edited_at))}`);
    lines.push(`Revised from ${esc(x.revised_from_number)}${x.revision_reason?' — '+esc(x.revision_reason):''}`);
  }
  if(x.status==='VOID'){
    const what=x.revised_to_number?`Replaced by ${esc(x.revised_to_number)}`:'Cancelled';
    lines.push(`${what} — ${esc(x.voided_by_name||'-')} on ${esc(fmtTime(x.voided_at))}`);
  }
  return lines.length?`<div class="small muted">${lines.join('<br>')}</div>`:'';
}

async function editableSales(){
  const view=state.salesView==='VOID'?'VOID':'FINALIZED';
  const d=await api('/api/invoices?start=1900-01-01&end='+dateISO()+'&status='+view);
  const rows=d.map(x=>{
    const ref=esc(JSON.stringify(String(x.invoice_number??'')));
    const actions=x.status==='FINALIZED'
      ?`<button class="button" onclick="startEditBill(${x.id})">Edit</button><button class="button" onclick="returnInvoice(${x.id})">Return</button><button class="button danger" onclick="voidSale(${x.id},${ref})">Delete</button>`
      :'';
    return `<tr><td><strong>${esc(x.invoice_number)}</strong>${billHistory(x)}</td><td>${esc(x.invoice_date)}</td><td>${esc(x.customer_name_snapshot)}</td><td>${esc(x.billed_by_name||'-')}<div class="small muted">${esc(fmtTime(x.created_at))}</div></td><td>${money(x.grand_total)}</td><td>${money(x.amount_received)}</td><td><div class="row"><button class="button" onclick="window.open('/api/invoice-pdf/${x.id}','_blank')">PDF</button>${actions}</div></td></tr>`;
  }).join('');
  $('#app').innerHTML=shell('Sales',`<div class="card"><div class="between"><div><h3>Invoices</h3><div class="small muted">Edit re-issues the bill with a new number and keeps the original as cancelled. Delete voids the sale and restores stock.</div></div><div class="row"><select class="select" onchange="state.salesView=this.value;sales()"><option value="FINALIZED" ${view==='FINALIZED'?'selected':''}>Active bills</option><option value="VOID" ${view==='VOID'?'selected':''}>Cancelled / edited bills</option></select><button class="button primary" onclick="cancelEditBill(false);go('billing');newBill()">+ New Bill</button></div></div><br><div class="table-wrap"><table class="table"><thead><tr><th>Invoice</th><th>Date</th><th>Customer</th><th>Billed by</th><th>Total</th><th>Received</th><th>Actions</th></tr></thead><tbody>${rows||'<tr><td colspan="7" class="muted">No bills.</td></tr>'}</tbody></table></div></div><div id="modal" class="modal"></div>`);
}

async function startEditBill(id){
  try{
    const d=await api('/api/invoices/'+id);
    const inv=d.invoice;
    if(inv.status!=='FINALIZED')return toast('Only active bills can be edited.');
    const missing=d.items.filter(it=>!state.products.find(p=>p.id===it.product_id));
    if(missing.length)return toast('Cannot edit: these products are no longer active: '+missing.map(m=>m.product_name_snapshot).join(', '));
    const walkIn=state.settings?.walk_in_name||'Walk-in Customer';
    const name=inv.customer_id&&inv.customer_name_snapshot!==walkIn?inv.customer_name_snapshot:'';
    state.editing={id:inv.id,number:inv.invoice_number,customer_id:inv.customer_id,customer_name:name,customer_phone:inv.customer_phone||'',payments:(d.payments||[]).map(p=>({mode:p.mode,amount:p.amount})),notes:inv.notes||''};
    state.cart=d.items.map(it=>({product_id:it.product_id,qty:it.qty_input,sell_unit:it.sell_unit}));
    state.billDiscount=Number(inv.discount||0);
    state.customerName=name;
    state.customerPhone=state.editing.customer_phone;
    state.selectedCustomer=null;
    go('billing');
  }catch(e){toast(e.message)}
}

function cancelEditBill(rerender=true){
  if(!state.editing)return;
  state.editing=null;state.cart=[];state.billDiscount=0;state.customerName='';state.customerPhone='';
  if(rerender){toast('Edit cancelled');go('sales')}
}

let baseBilling, baseNewBill, baseOpenPayment, baseFinalizeSale;

function editAwareBilling(){
  baseBilling();
  if(!state.editing)return;
  $('#holdCurrentBill')?.remove();
  $('#app button[onclick="showHeldBills()"]')?.remove();
  $('.billing-actions')?.insertAdjacentHTML('afterend',`<div class="notice warn" style="margin-bottom:12px">Editing bill <strong>${esc(state.editing.number)}</strong>. Add, remove or change quantities, then complete payment. The original bill will be kept as cancelled. <button class="button" onclick="cancelEditBill()">Cancel edit</button></div>`);
  const pay=$('.bill-payment-button');if(pay)pay.textContent='Save edited bill';
}

function editAwareNewBill(){
  if(state.editing){state.editing=null}
  return baseNewBill();
}

async function editAwareOpenPayment(){
  await baseOpenPayment();
  if(!state.editing)return;
  const payable=roundCurrency(cartSubtotal()-activeBillDiscount());
  const old=state.editing.payments.filter(p=>p.amount>0);
  const oldTotal=roundCurrency(old.reduce((a,p)=>a+p.amount,0));
  if(old.length&&Math.abs(oldTotal-payable)<=0.01){
    $('#payRows').innerHTML='';
    old.forEach(p=>addPayRow(p.amount,p.mode));
  }
  const notes=$('#billNotes');if(notes&&!notes.value)notes.value=state.editing.notes;
  notes?.closest('label')?.insertAdjacentHTML('afterend','<br><label>Reason for edit (required)<input class="input" id="editReason" placeholder="e.g. customer added 2 boxes"></label>');
  const finalize=$('#modal button.primary[onclick^="finalizeSale"]');if(finalize)finalize.textContent='Save edited bill';
  $('#modal h3').textContent='Edit '+state.editing.number;
}

async function editAwareFinalizeSale(total){
  if(!state.editing)return baseFinalizeSale(total);
  const reason=($('#editReason')?.value||'').trim();
  if(reason.length<3)return toast('Enter a reason for editing this bill.');
  const phone=(state.customerPhone||'').trim();
  if(phone&&!/^\d{10}$/.test(phone))return toast('Mobile number must be exactly 10 digits.');
  const billWindow=window.open('about:blank','_blank');
  try{
    const discount=activeBillDiscount(),payable=roundCurrency(cartSubtotal()-discount);
    const pays=$$('.payamt').map((el,i)=>({amount:+el.value,mode:$$('.paymode')[i].value})).filter(x=>x.amount>0);
    const sum=pays.reduce((a,x)=>a+x.amount,0);
    if(Math.abs(sum-payable)>0.01||Math.abs(total-payable)>0.01)throw new Error('Payment total must match the amount after discount.');
    const name=(state.customerName||'').trim();
    const sameCustomer=name===state.editing.customer_name&&phone===state.editing.customer_phone;
    const d=await api(`/api/invoices/${state.editing.id}/edit`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({customer_id:sameCustomer?state.editing.customer_id:null,customer_name:name,customer_phone:phone,items:state.cart,discount,payments:pays,notes:$('#billNotes').value,reason})});
    if(billWindow)billWindow.location='/api/invoice-pdf/'+d.invoice_id;
    closeModal();
    state.editing=null;state.cart=[];state.billDiscount=0;state.customerName='';state.customerPhone='';
    await loadBasics();
    toast(`${d.previous_invoice_number} edited — new bill ${d.invoice_number}`);
    go('sales');
  }catch(err){if(billWindow)billWindow.close();toast(err.message)}
}

function applyBillEdit(){
  // Capture the screens ui_fixes.js installed (at +100ms/+150ms) before wrapping them.
  baseBilling=billing;baseNewBill=newBill;baseOpenPayment=openPayment;baseFinalizeSale=finalizeSale;
  billing=editAwareBilling;newBill=editAwareNewBill;openPayment=editAwareOpenPayment;finalizeSale=editAwareFinalizeSale;sales=editableSales;
  if(state.user)render();
}

window.addEventListener('load',()=>setTimeout(applyBillEdit,250));
