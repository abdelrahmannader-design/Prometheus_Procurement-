import importlib.util
import pathlib
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
APP_PATH=ROOT/'Prometheus_V10_9_10.py'
spec=importlib.util.spec_from_file_location('prometheus_v1099',APP_PATH)
mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class V1096EnhancementTests(unittest.TestCase):
    def test_local_purchase_is_fifo_lot_at_all_in_cost(self):
        app=mod.App.__new__(mod.App)
        app.state_obj={'contracts':{},'local_purchases':[{
            'id':7,'date':'2026-09-01','supplier':'Local A','commodity':'CORN',
            'origin':'EGYPT','qty_mt':1000,'price_egp_mt':14000,'transport_egp_mt':300}],
            'settings':{},'freight_rates':{},'commodities':{}}
        lots=app._fifo_contract_lots(as_of=mod.dt.date(2026,9,9))
        lp=next(x for x in lots if x.get('source_type')=='LOCAL_PURCHASE')
        self.assertEqual(lp['original_mt'],1000)
        self.assertEqual(lp['cost_egp_mt'],14300)
        self.assertEqual(lp['delivery_date'],'2026-09-01')

    def test_local_source_scenario_compares_to_import(self):
        out=mod._core_calculate_inventory_scenario(
            current_remaining_mt=1000,avg_inventory_cost_egp_mt=14000,
            local_base_egp_mt=14200,local_transport_egp_mt=300,
            cbot=500,premium=180,conversion_factor=.3937,fx=50,
            freight_input_egp_mt=400,freight_mode='ALL_IN',other_fees_egp_mt=200,
            purchase_qty_mt=500,purchase_source='LOCAL')
        self.assertEqual(out['purchase_source'],'LOCAL')
        self.assertEqual(out['scenario_purchase_cost_egp_mt'],14500)
        self.assertIsNotNone(out['import_benchmark_cost_egp_mt'])
        self.assertAlmostEqual(out['scenario_saving_egp_mt'],out['import_benchmark_cost_egp_mt']-14500,places=6)

    def _workbook_app(self):
        app=mod.App.__new__(mod.App)
        app.state_obj={'market_data':{'fx':{'price':50}},'contracts':{},'local_purchases':[]}
        fifo={'CORN':{'commodity':'CORN','remaining_mt':1000,'weighted_avg_cost_egp_mt':14000,
            'local_egp_mt':14500,'inventory_edge_egp_mt':500,'inventory_edge_egp':500000,
            'cbot':500,'premium':180,'current_fx':50,'replacement_fees_egp_mt':600,
            'replacement_cost_egp_mt':13987,'daily_consumption_rate':100,'coverage_days':10,
            'layers':[{'source_type':'LOCAL_PURCHASE','contract_ref':'LOCAL #1','supplier':'Local A','commodity':'CORN',
                'delivery_date':'2026-09-01','original_mt':1000,'consumed_mt':0,'remaining_mt':1000,
                'cost_egp_mt':14000,'status':'Local Purchase','cost_basis':'local actual','cost_formula':'14000'}]}}
        app._fifo_portfolio=lambda as_of=None: fifo
        app._home_commodity_options=lambda:['CORN']
        app._fifo_market_inputs_for_layer=lambda base,row,layer:{'cbot':500,'premium':180,'factor':.3937,'fx':50,'fees':600,'local':14500,'local_date':'2026-09-09'}
        return app

    def test_fifo_workbook_is_formula_driven_and_contains_local_source(self):
        app=self._workbook_app(); wb=app._build_fifo_inventory_workbook('CORN')
        self.assertIn('FIFO Summary',wb.sheetnames); self.assertIn('FIFO Layers',wb.sheetnames)
        ws=wb['FIFO Layers']; self.assertEqual(ws['B5'].value,'Local')
        self.assertTrue(str(ws['K5'].value).startswith('=')); self.assertTrue(str(ws['M5'].value).startswith('='))
        summary=wb['FIFO Summary']; self.assertTrue(str(summary['B6'].value).startswith('=SUMIF'))
        self.assertGreaterEqual(len(summary._charts),1)

    def test_scenario_workbook_is_formula_driven_and_has_fifo_sources(self):
        app=self._workbook_app()
        data={'commodity':'CORN','inputs':{'purchase_source':'LOCAL','cbot':500,'fx':50,'premium':180,'factor':.3937,
              'local_base':14200,'local_transport':300,'freight':400,'freight_mode':'ALL_IN','vat':14,'other_fees':200,
              'purchase_qty':500,'consumption_qty':0,'horizon':10,'daily_consumption':100,'proposed_cif':None,
              'current_remaining':1000,'current_avg_cost':14000}}
        wb=app._build_scenario_workbook(data); ws=wb['Scenario Lab']
        self.assertEqual(wb.sheetnames[:3],['Cost Summary','Scenario Lab','Current FIFO Sources'])
        summary=wb['Cost Summary']
        self.assertEqual(summary['A18'].value,'LOCAL COST')
        self.assertEqual(summary['D18'].value,'IMPORT COST')
        self.assertEqual(summary['A25'].value,'COST FORMULA MAP')
        self.assertTrue(str(summary['E39'].value).startswith("='Scenario Lab'!"))
        formulas=[c.value for row in ws.iter_rows() for c in row if isinstance(c.value,str) and c.value.startswith('=')]
        self.assertGreaterEqual(len(formulas),10)
        self.assertIn('Current FIFO Sources',wb.sheetnames)
        self.assertEqual(wb['Current FIFO Sources']['A4'].value,'Local')
        self.assertGreaterEqual(len(ws._charts),1)

    def test_replacement_intake_prefers_supplier_setup_and_keeps_clearance_separate(self):
        app=mod.App.__new__(mod.App)
        app.state_obj={
            'contracts':{'C1':{'supplier':'ADM Medsofts','commodity':'CORN-BRZ',
                               'intake_mode':'DIRECT','discharge_egp_mt':366.50,'clearance_egp_mt':200.00}},
            'suppliers':{'ADM Medsofts':{'CORN':{'direct_egp_mt':245.63,'indirect_egp_mt':320.87}}}
        }
        fifo={'commodity':'CORN','layers':[{'contract_id':'C1','supplier':'ADM Medsofts',
               'commodity':'CORN-BRZ','remaining_mt':3000}]}
        fees=app._fifo_current_intake_components(fifo)
        self.assertAlmostEqual(fees['direct_egp_mt'],245.63,places=6)
        self.assertAlmostEqual(fees['indirect_egp_mt'],320.87,places=6)
        self.assertEqual(fees['intake_mode'],'DIRECT')
        self.assertAlmostEqual(fees['selected_intake_egp_mt'],245.63,places=6)
        self.assertAlmostEqual(fees['clearance_egp_mt'],200.00,places=6)
        self.assertAlmostEqual(fees['selected_intake_egp_mt']+fees['clearance_egp_mt'],445.63,places=6)
        self.assertNotAlmostEqual(fees['selected_intake_egp_mt'],fees['direct_egp_mt']+fees['indirect_egp_mt'],places=6)
        self.assertEqual(fees['sources'][0]['source'],'supplier setup')

    def test_scenario_uses_contract_freight_before_commodity_default(self):
        app=mod.App.__new__(mod.App)
        app.state_obj={
            'contracts':{'C1':{'name':'460/20048300','freight_mode':'DETAILED',
                               'freight_base_egp_mt':425.53,'freight_vat_pct':14.0,
                               'freight_egp_mt':485.1042}},
            'commodity_freight_defaults':{'CORN':323.13}, 'ui':{}
        }
        app._hd_ref=lambda cid,c: c.get('name') or cid
        fifo={'commodity':'CORN','layers':[{'contract_id':'C1','remaining_mt':3000}]}
        fr=app._fifo_current_freight_components(fifo)
        self.assertEqual(fr['mode'],'DETAILED')
        self.assertAlmostEqual(fr['input_egp_mt'],425.53,places=6)
        self.assertAlmostEqual(fr['vat_pct'],14.0,places=6)
        self.assertAlmostEqual(fr['effective_egp_mt'],485.1042,places=6)
        self.assertEqual(fr['refs'],['460/20048300'])

    def test_scenario_fx_can_use_form4_locked_or_current_market(self):
        app=mod.App.__new__(mod.App)
        app.state_obj={
            'market_data':{'fx':{'price':51.34}},
            'contracts':{'C1':{'name':'460/20048300','form4_fx':51.0}},
        }
        app._hd_ref=lambda cid,c: c.get('name') or cid
        fifo={'commodity':'CORN','layers':[{'contract_id':'C1','remaining_mt':3000}]}
        fx=app._fifo_current_fx_components(fifo)
        self.assertAlmostEqual(fx['current_fx'],51.34,places=6)
        self.assertAlmostEqual(fx['locked_fx'],51.0,places=6)
        self.assertEqual(fx['locked_refs'],['460/20048300'])
        self.assertEqual(fx['locked_covered_mt'],3000)

    def test_scenario_excel_exposes_fx_source_and_selector_formula(self):
        app=self._workbook_app()
        data={'commodity':'CORN','inputs':{'purchase_source':'IMPORT','cbot':532,'fx_source':'FORM 4 LOCKED','fx':51.0,'current_fx':51.34,'locked_fx':51.0,'locked_fx_source':'460/20048300','premium':194.25,'factor':.3937,
              'local_base':14500,'local_transport':396.88,'freight':425.53,'freight_mode':'DETAILED','vat':14,
              'intake_mode':'DIRECT','direct_fee':245.63,'indirect_fee':320.87,'selected_intake_fee':245.63,
              'clearance_fee':225.0,'other_fees':470.63,'purchase_qty':0,'consumption_qty':0,'horizon':30,'daily_consumption':500,'proposed_cif':None,
              'current_remaining':2000,'current_avg_cost':15355.63}}
        wb=app._build_scenario_workbook(data); ws=wb['Scenario Lab']
        rows={ws.cell(r,1).value:r for r in range(6,50) if ws.cell(r,1).value}
        self.assertEqual(ws.cell(rows['FX Source'],2).value,'FORM 4 LOCKED')
        self.assertEqual(ws.cell(rows['Current Market FX'],2).value,51.34)
        self.assertEqual(ws.cell(rows['Form 4 Locked FX'],2).value,51.0)
        self.assertEqual(ws.cell(rows['Form 4 FX Source'],2).value,'460/20048300')
        fx_formula=str(ws.cell(rows['FX'],2).value).upper()
        self.assertTrue(fx_formula.startswith('='))
        self.assertIn('CURRENT MARKET',fx_formula)
        self.assertIn('FORM 4 LOCKED',fx_formula)
        self.assertNotIn('IF(',fx_formula)

    def test_scenario_excel_adds_local_implied_premium_bridge(self):
        app=self._workbook_app()
        data={'commodity':'CORN','inputs':{'purchase_source':'IMPORT','cbot':532,'fx_source':'FORM 4 LOCKED','fx':51.0,'current_fx':51.34,'locked_fx':51.0,'locked_fx_source':'460/20048300','premium':194.25,'factor':.3937,
              'local_base':14500,'local_transport':396.88,'freight':425.53,'freight_mode':'DETAILED','vat':14,
              'intake_mode':'DIRECT','direct_fee':245.63,'indirect_fee':320.87,'selected_intake_fee':245.63,
              'clearance_fee':225.0,'other_fees':470.63,'purchase_qty':0,'consumption_qty':0,'horizon':30,'daily_consumption':500,'proposed_cif':None,
              'current_remaining':2000,'current_avg_cost':15355.63}}
        wb=app._build_scenario_workbook(data); ws=wb['Scenario Lab']; summary=wb['Cost Summary']
        result_rows={ws.cell(r,4).value:r for r in range(6,55) if ws.cell(r,4).value}
        scenario_label='Scenario Import Premium (c/bu)'
        implied_label='Implied Local Premium (c/bu)'
        gap_label='Premium Gap vs Local (c/bu)'
        for label in (scenario_label,'Local-Equivalent CIF USD/MT',implied_label,gap_label):
            self.assertIn(label,result_rows)
            self.assertTrue(str(ws.cell(result_rows[label],5).value).startswith('='))
        implied_formula=str(ws.cell(result_rows[implied_label],5).value)
        self.assertIn('Local-Equivalent CIF USD/MT', result_rows)
        self.assertNotIn('IF(', implied_formula.upper())
        self.assertEqual(summary['A37'].value,'CBOT vs LOCAL — PREMIUM EQUIVALENT')
        self.assertTrue(str(summary['B41'].value).startswith("='Scenario Lab'!"))
        # Same arithmetic as Basis Tracker when its editable Expenses equals
        # Scenario freight + selected intake + clearance.
        local_all_in=14500+396.88
        expenses=425.53*1.14+245.63+225.0
        implied=((local_all_in-expenses)/51.0)/.3937-532
        self.assertAlmostEqual(implied,162.32512065024127,places=5)
        self.assertAlmostEqual(194.25-implied,31.924879349758726,places=5)

    def test_scenario_excel_keeps_intake_alternatives_and_clearance_separate(self):
        app=self._workbook_app()
        data={'commodity':'CORN','inputs':{'purchase_source':'IMPORT','cbot':532,'fx':51.34,'premium':194.25,'factor':.3937,
              'local_base':14500,'local_transport':396.88,'freight':323.13,'freight_mode':'DETAILED','vat':14,
              'intake_mode':'DIRECT','direct_fee':245.63,'indirect_fee':320.87,'selected_intake_fee':245.63,
              'clearance_fee':200.00,'other_fees':445.63,
              'purchase_qty':5000,'consumption_qty':0,'horizon':30,'daily_consumption':500,'proposed_cif':None,
              'current_remaining':2000,'current_avg_cost':15355.63}}
        wb=app._build_scenario_workbook(data); ws=wb['Scenario Lab']
        input_rows={ws.cell(r,1).value:r for r in range(6,45) if ws.cell(r,1).value}
        result_rows={ws.cell(r,4).value:r for r in range(6,45) if ws.cell(r,4).value}
        self.assertEqual(ws.cell(input_rows['Intake Type'],2).value,'DIRECT')
        self.assertEqual(ws.cell(input_rows['Direct Intake EGP/MT'],2).value,245.63)
        self.assertEqual(ws.cell(input_rows['Indirect Intake EGP/MT'],2).value,320.87)
        self.assertEqual(ws.cell(input_rows['Clearance EGP/MT'],2).value,200.0)
        selected_formula=str(ws.cell(result_rows['Selected Intake EGP/MT'],5).value).upper()
        self.assertNotIn('IF(', selected_formula)
        self.assertIn('DIRECT', selected_formula)
        self.assertIn('INDIRECT', selected_formula)
        other_formula=ws.cell(result_rows['Other Import Fees EGP/MT'],5).value
        self.assertEqual(other_formula,
            f"=E{result_rows['Selected Intake EGP/MT']}+E{result_rows['Clearance EGP/MT']}")
        for label in ('Local All-In EGP/MT','Import Benchmark EGP/MT','Saving / Loss EGP/MT',
                      'Total Scenario Impact EGP','Post-Purchase Local Edge EGP/MT',
                      'Current FIFO Edge vs Local EGP/MT'):
            formula=str(ws.cell(result_rows[label],5).value).upper()
            self.assertNotIn('IF(',formula,label)

    def test_digest_catalog_and_ceo_tab_are_present(self):
        app=mod.App.__new__(mod.App)
        ids=[x[0] for x in app._ceo_digest_export_catalog()]
        for required in ('ceo_brief','fifo','scenario','inventory_market','local_purchases','contracts','finance','basis','state'):
            self.assertIn(required,ids)
        source=APP_PATH.read_text(encoding='utf-8')
        self.assertIn("CEO Email Digest",source)
        self.assertIn('Grouped email',source); self.assertIn('Separate emails',source)

if __name__=='__main__': unittest.main()

class V1097InventoryMappingAndDateOrderTests(unittest.TestCase):
    def test_inventory_market_row_mapping_starts_with_source_then_ref(self):
        app=mod.App.__new__(mod.App)
        row={
            'source_type':'IMPORT_CONTRACT','ref':'460/20048300','supplier':'ADM Medsofts',
            'commodity':'CORN-BRZ','origin':'BRAZIL','status':'Open','pricing_status':'UNPRICED',
            'remaining_mt':3000,'fifo_cost':15306,'fifo_cost_basis':'live',
            'fifo_cost_formula_short':'live formula','live_cbot':529.5,'premium':194.25,
            'formula':'formula','fx_today':50.45,'freight_today':426,'replacement_cost':15494,
            'local':15097,'edge_local_mt':-209,'edge_repl_mt':188,'decision':'Mixed'
        }
        vals=app._inventory_market_row_values(row,'15,097')
        self.assertEqual(len(vals),20)
        self.assertEqual(vals[:7],('IMPORT','460/20048300','ADM Medsofts','CORN-BRZ','BRAZIL','Open','UNPRICED'))
        self.assertEqual(vals[7],'3,000')
        self.assertEqual(vals[16],'15,097')

    def test_local_purchase_mapping_is_not_shifted(self):
        app=mod.App.__new__(mod.App)
        row={'source_type':'LOCAL_PURCHASE','ref':'LOCAL #14','supplier':'COFCO','commodity':'CORN-BRZ',
             'origin':'Local','status':'Local Purchase','pricing_status':'LOCAL ACTUAL','remaining_mt':1000,
             'fifo_cost':15026,'fifo_cost_basis':'local_actual','fifo_cost_formula_short':'Local actual',
             'live_cbot':529.5,'premium':194.25,'formula':'portfolio benchmark','fx_today':50.45,
             'freight_today':0,'replacement_cost':15378,'local':15097,'edge_local_mt':71,
             'edge_repl_mt':352,'decision':'Ahead'}
        vals=app._inventory_market_row_values(row,'15,097')
        self.assertEqual(vals[0],'LOCAL PURCHASE')
        self.assertEqual(vals[1],'LOCAL #14')
        self.assertEqual(vals[2],'COFCO')
        self.assertEqual(vals[3],'CORN-BRZ')
        self.assertEqual(vals[4],'Local')

    def test_date_order_helper(self):
        self.assertTrue(mod._date_order_newest_first(mod.DATE_ORDER_NEWEST))
        self.assertFalse(mod._date_order_newest_first(mod.DATE_ORDER_OLDEST))
        self.assertTrue(mod._date_order_newest_first(''))

class _FakeVar:
    def __init__(self, value=''): self.value=value
    def get(self): return self.value
    def set(self, value): self.value=value

class _FakeTree:
    def __init__(self): self.rows=[]
    def get_children(self, *args): return list(range(len(self.rows)))
    def delete(self, *args): self.rows=[]
    def insert(self, parent, where, **kwargs): self.rows.append(kwargs.get('values'))

class V1097DateSortTableBehaviorTests(unittest.TestCase):
    def test_local_prices_switches_newest_and_oldest(self):
        app=mod.App.__new__(mod.App); app.tk=None
        app.state_obj={'local_prices':[
            {'date':'2026-07-28','commodity':'CORN','price_egp_mt':14000,'transport_egp_mt':300},
            {'date':'2026-09-08','commodity':'CORN','price_egp_mt':15000,'transport_egp_mt':300},
        ],'ui':{},'commodities':{}}
        app.lp_tree=_FakeTree(); app.lp_order_var=_FakeVar(mod.DATE_ORDER_NEWEST)
        app.refresh_local_monthly_contract_values=lambda: None
        app.refresh_local_prices_tree()
        self.assertEqual(app.lp_tree.rows[0][0],'2026-09-08')
        app.lp_order_var.set(mod.DATE_ORDER_OLDEST); app.refresh_local_prices_tree()
        self.assertEqual(app.lp_tree.rows[0][0],'2026-07-28')

    def test_fx_history_switches_newest_and_oldest(self):
        app=mod.App.__new__(mod.App); app.tk=None
        app.state_obj={'fx_history':[
            {'date':'2026-07-28','rate':49.0,'source':'manual'},
            {'date':'2026-09-08','rate':50.9,'source':'manual'},
        ],'ui':{}}
        app._fxh_tree=_FakeTree(); app._fxh_status_var=_FakeVar(); app._fxh_order_var=_FakeVar(mod.DATE_ORDER_NEWEST)
        app._refresh_fx_history_tree(); self.assertEqual(app._fxh_tree.rows[0][0],'2026-09-08')
        app._fxh_order_var.set(mod.DATE_ORDER_OLDEST); app._refresh_fx_history_tree(); self.assertEqual(app._fxh_tree.rows[0][0],'2026-07-28')

    def test_cbot_history_switches_newest_and_oldest(self):
        app=mod.App.__new__(mod.App); app.tk=None
        app.state_obj={'cbot_history':[
            {'date':'2026-07-28','commodity':'CORN','price':490.0,'source':'manual'},
            {'date':'2026-09-08','commodity':'CORN','price':530.0,'source':'manual'},
        ],'ui':{}}
        app._cbot_hist_tree=_FakeTree(); app._cbot_status_var=_FakeVar(); app._cbot_order_var=_FakeVar(mod.DATE_ORDER_NEWEST)
        app._refresh_cbot_history_trees(); self.assertEqual(app._cbot_hist_tree.rows[0][0],'2026-09-08')
        app._cbot_order_var.set(mod.DATE_ORDER_OLDEST); app._refresh_cbot_history_trees(); self.assertEqual(app._cbot_hist_tree.rows[0][0],'2026-07-28')

class V1098OpenUnpricedExposureTests(unittest.TestCase):
    def _app(self):
        app=mod.App.__new__(mod.App)
        app.state_obj={
            'contracts':{
                'C1':{'name':'Open unpriced past date','status':'Open','commodity':'CORN-BRZ','qty_mt':3000,
                      'delivery_date':'2026-08-01','pricing_status':'UNPRICED','priced':False,'premium_cents':190},
                'C2':{'name':'Open priced','status':'Open','commodity':'CORN-ARG','qty_mt':2000,
                      'delivery_date':'2026-10-01','pricing_status':'PRICED','priced':True,'cif_usd_mt':280},
                'C3':{'name':'Closed unpriced','status':'Closed','commodity':'CORN-BRZ','qty_mt':1000,
                      'delivery_date':'2026-07-01','pricing_status':'UNPRICED','priced':False},
            },
            'local_purchases':[], 'consumption_log':[], 'consumption':{},
            'market_data':{'fx':{'price':50},'cbot_quotes':{'CORN':{'price':530}}},
            'ui':{'inventory_auto_estimate_daily':False}, 'commodities':{}, 'suppliers':{},
            'settings':{}, 'freight_rates':{}, 'local_prices':[]
        }
        return app

    def test_explicit_unpriced_status_overrides_stale_cif(self):
        app=self._app()
        c={'status':'Open','qty_mt':3000,'pricing_status':'UNPRICED','priced':True,'cif_usd_mt':280}
        self.assertEqual(app._contract_pricing_status(c),'UNPRICED')
        self.assertEqual(app._home_contract_pricing_split(c),(0.0,3000.0))

    def test_open_unpriced_is_counted_even_when_delivery_date_is_past(self):
        app=self._app()
        exp=app.portfolio_exposure()
        self.assertEqual(exp['open_mt'],5000)
        self.assertEqual(exp['unpriced_mt'],3000)
        self.assertEqual(exp['priced_mt'],2000)

    def test_partial_pricing_lots_split_quantity(self):
        app=self._app()
        c={'status':'Open','qty_mt':5000,'pricing_status':'PARTIAL','pricing_lots':[{'qty_mt':2000,'premium_cents':180}]}
        self.assertEqual(app._contract_pricing_status(c),'PARTIAL')
        self.assertEqual(app._home_contract_pricing_split(c),(2000.0,3000.0))

class V1099FXExposureBreakdownTests(unittest.TestCase):
    def _app(self):
        app=mod.App.__new__(mod.App)
        app.state_obj={'contracts':{
            'C1':{'name':'CORN-A','status':'Open','commodity':'CORN-BRZ','qty_mt':6000,'form4_fx':50.40,'pricing_status':'UNPRICED'},
            'C2':{'name':'CORN-B','status':'Open','commodity':'CORN-ARG','qty_mt':5000,'form4_fx':50.55,'pricing_status':'UNPRICED'},
            'C3':{'name':'SBM-FLOAT','status':'Open','commodity':'SBM','qty_mt':1000,'form4_fx':None,'pricing_status':'UNPRICED','delivery_date':'2026-08-01'},
            'C4':{'name':'CLOSED-IGNORE','status':'Closed','commodity':'CORN','qty_mt':10000,'form4_fx':None,'pricing_status':'UNPRICED'},
        }}
        return app

    def test_92pct_example_is_auditable_to_contract_level(self):
        app=self._app(); fx=app._home_fx_hedge_coverage('ALL')
        self.assertEqual(fx['open_qty'],12000)
        self.assertEqual(fx['hedged_qty'],11000)
        self.assertEqual(fx['unhedged_qty'],1000)
        self.assertAlmostEqual(fx['pct'],91.6666666667,places=5)
        self.assertEqual(fx['unhedged_contracts'],1)
        self.assertEqual(fx['unhedged'][0]['ref'],'SBM-FLOAT')
        self.assertEqual(fx['unhedged'][0]['qty_mt'],1000)

    def test_fx_breakdown_is_by_base_commodity_and_ignores_delivery_timing(self):
        app=self._app(); fx=app._home_fx_hedge_coverage('ALL')
        self.assertEqual(fx['by_commodity']['CORN']['open_qty'],11000)
        self.assertEqual(fx['by_commodity']['CORN']['unhedged_qty'],0)
        self.assertEqual(fx['by_commodity']['CORN']['pct'],100.0)
        self.assertEqual(fx['by_commodity']['SBM']['open_qty'],1000)
        self.assertEqual(fx['by_commodity']['SBM']['unhedged_qty'],1000)
        self.assertEqual(fx['by_commodity']['SBM']['pct'],0.0)
        # Past delivery date does not make an open FX exposure disappear.
        self.assertEqual(app._home_fx_hedge_coverage('SBM')['unhedged_qty'],1000)

    def test_ceo_brief_labels_separate_fx_from_cbot_pricing(self):
        source=APP_PATH.read_text(encoding='utf-8')
        for text in ('FX secured','FX still floating','Uncovered FX contracts','CBOT unpriced exposure'):
            self.assertIn(text,source)
