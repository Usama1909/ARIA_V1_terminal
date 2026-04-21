import numpy as np,pandas as pd,yfinance as yf,pickle
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score
from xgboost import XGBClassifier
import torch,torch.nn as nn,warnings
warnings.filterwarnings('ignore')

SYMBOLS={'BTC':'BTC-USD','ETH':'ETH-USD','AAPL':'AAPL','NVDA':'NVDA','TSLA':'TSLA','GLD':'GLD'}
MODEL_PATH='/root'

def build_features(df):
    prices=df['Close'];volume=df['Volume'];high=df['High'];low=df['Low']
    tr1=high-low;tr2=abs(high-prices.shift(1));tr3=abs(low-prices.shift(1))
    atr=pd.concat([tr1,tr2,tr3],axis=1).max(axis=1).rolling(14).mean()
    delta=prices.diff()
    gain=delta.where(delta>0,0).rolling(14).mean()
    loss=-delta.where(delta<0,0).rolling(14).mean()
    rsi=100-(100/(1+gain/loss))
    ema_fast=prices.ewm(span=12).mean();ema_slow=prices.ewm(span=26).mean()
    macd=ema_fast-ema_slow;macd_hist=macd-macd.ewm(span=9).mean()
    ma_20=prices.rolling(20).mean();std_20=prices.rolling(20).std()
    bb_upper=ma_20+(std_20*2);bb_lower=ma_20-(std_20*2);ma_50=prices.rolling(50).mean()
    volatility=prices.pct_change().rolling(10).std()
    bb_position=(prices-bb_lower)/(bb_upper-bb_lower)
    ma_distance=(ma_20-ma_50)/ma_50
    pc5=prices.pct_change(5);pc10=prices.pct_change(10);pc24=prices.pct_change(24)
    rsi_mom=rsi.diff();vol_ratio=volume/volume.rolling(20).mean()
    vol_trend=volume.rolling(5).mean()/volume.rolling(20).mean()
    p4h=prices.rolling(4).mean();d4h=p4h.diff()
    g4h=d4h.where(d4h>0,0).rolling(14).mean()
    l4h=-d4h.where(d4h<0,0).rolling(14).mean()
    rsi4h=100-(100/(1+g4h/l4h))
    h24=prices.rolling(24).max();l24=prices.rolling(24).min()
    dfh=(prices-h24)/h24;dfl=(prices-l24)/l24
    r24=h24-l24
    rpos=np.where(r24>0,(prices-l24)/r24,0.5)
    cr=(high-low)/prices
    ccp=(prices-low)/(high-low+1e-9)
    uw=(high-prices)/(high-low+1e-9);lw=(prices-low)/(high-low+1e-9)
    adx=abs(ma_distance)/volatility.replace(0,np.nan)
    zs=(prices-prices.rolling(20).mean())/prices.rolling(20).std()
    m5=prices/prices.shift(5)-1;m10=prices/prices.shift(10)-1
    atrp=atr/prices
    pc=prices.pct_change()
    bvf=np.where(pc>0.001,0.9,np.where(pc<-0.001,0.1,np.where(pc>0,0.6,np.where(pc<0,0.4,0.5))))
    bv=volume*bvf;ofi=abs(bv-volume*(1-bvf))
    vr=ofi.rolling(50).sum()/volume.rolling(50).sum()
    v10=vr.quantile(0.10);v90=vr.quantile(0.90)
    vn=((vr-v10)/(v90-v10+1e-9)).clip(0,1)
    vs=np.where(vn>0.7,1,np.where(vn<0.3,-1,0))
    fn=['rsi','macd','macd_hist','volatility','bb_position','ma_distance',
        'price_change_5','price_change_10','price_change_24','rsi_momentum',
        'volume_ratio','volume_trend','rsi_4h','dist_from_high','dist_from_low',
        'range_position','candle_range','candle_close_pos','upper_wick','lower_wick',
        'adx_proxy','z_score','momentum_5','momentum_10','atr_pct','vpin_norm','vpin_signal']
    feat=pd.DataFrame({'rsi':rsi,'macd':macd,'macd_hist':macd_hist,'volatility':volatility,
        'bb_position':bb_position,'ma_distance':ma_distance,'price_change_5':pc5,
        'price_change_10':pc10,'price_change_24':pc24,'rsi_momentum':rsi_mom,
        'volume_ratio':vol_ratio,'volume_trend':vol_trend,'rsi_4h':rsi4h,
        'dist_from_high':dfh,'dist_from_low':dfl,
        'range_position':pd.Series(rpos,index=prices.index),
        'candle_range':cr,
        'candle_close_pos':pd.Series(ccp.values if hasattr(ccp,'values') else ccp,index=prices.index),
        'upper_wick':pd.Series(uw.values if hasattr(uw,'values') else uw,index=prices.index),
        'lower_wick':pd.Series(lw.values if hasattr(lw,'values') else lw,index=prices.index),
        'adx_proxy':adx,'z_score':zs,'momentum_5':m5,'momentum_10':m10,
        'atr_pct':atrp,'vpin_norm':vn,
        'vpin_signal':pd.Series(vs,index=prices.index)})
    return feat,atr,fn

def build_labels(prices,atr,tp=1.5,sl=1.0,h=24):
    labels=[]
    pa=prices.values;aa=atr.values
    for i in range(len(pa)-h):
        e=pa[i];ca=aa[i]
        if np.isnan(ca) or ca==0:labels.append(np.nan);continue
        tp_=e+ca*tp;sl_=e-ca*sl;out=np.nan
        for j in range(1,h+1):
            if i+j>=len(pa):break
            fp=pa[i+j]
            if fp>=tp_:out=1;break
            elif fp<=sl_:out=0;break
        if np.isnan(out):out=1 if pa[i+h-1]>e else 0
        labels.append(out)
    labels.extend([np.nan]*h)
    return pd.Series(labels,index=prices.index)

class TNN(nn.Module):
    def __init__(self,d=27):
        super().__init__()
        self.net=nn.Sequential(
            nn.Linear(d,128),nn.BatchNorm1d(128),nn.ReLU(),nn.Dropout(0.3),
            nn.Linear(128,64),nn.BatchNorm1d(64),nn.ReLU(),nn.Dropout(0.2),
            nn.Linear(64,32),nn.ReLU(),nn.Linear(32,2))
    def forward(self,x):return self.net(x)

def train_nn(Xtr,ytr,Xv,yv,epochs=100):
    m=TNN(Xtr.shape[1])
    opt=torch.optim.Adam(m.parameters(),lr=0.001)
    crit=nn.CrossEntropyLoss()
    sch=torch.optim.lr_scheduler.StepLR(opt,step_size=30,gamma=0.5)
    Xt=torch.FloatTensor(Xtr);yt=torch.LongTensor(ytr.astype(int))
    Xvt=torch.FloatTensor(Xv)
    best=0;bs=None
    for ep in range(epochs):
        m.train();opt.zero_grad()
        crit(m(Xt),yt).backward();opt.step();sch.step()
        if (ep+1)%20==0:
            m.eval()
            with torch.no_grad():
                acc=accuracy_score(yv,m(Xvt).argmax(dim=1).numpy())
                if acc>best:best=acc;bs={k:v.clone() for k,v in m.state_dict().items()}
            print(f"    NN ep{ep+1} val={acc:.3f}")
    if bs:m.load_state_dict(bs)
    return m,best

def train_sym(sym,ticker):
    print(f"\nTraining {sym}...")
    df=yf.Ticker(ticker).history(period='2y',interval='1h')
    if len(df)<500:print("  Not enough data");return None
    df=df.reset_index();df.columns=[c.replace(' ','_') for c in df.columns]
    print(f"  {len(df)} candles")
    feat,atr,fn=build_features(df)
    labels=build_labels(df['Close'],atr)
    d=feat[fn].copy();d['label']=labels;d=d.dropna()
    if len(d)<200:print("  Not enough clean data");return None
    X=d[fn].values;y=d['label'].values
    Xtr,Xt2,ytr,yt2=train_test_split(X,y,test_size=0.4,shuffle=False)
    Xv,Xte,yv,yte=train_test_split(Xt2,yt2,test_size=0.5,shuffle=False)
    print(f"  train={len(Xtr)} val={len(Xv)} test={len(Xte)}")
    print("  XGBoost...")
    xgb=XGBClassifier(n_estimators=300,max_depth=6,learning_rate=0.05,
        subsample=0.8,colsample_bytree=0.8,min_child_weight=3,
        gamma=0.1,eval_metric='logloss',verbosity=0,random_state=42)
    xgb.fit(Xtr,ytr,eval_set=[(Xv,yv)],verbose=False)
    xa=accuracy_score(yte,xgb.predict(Xte))
    print(f"  XGB={xa:.3f}")
    print("  Random Forest...")
    rf=RandomForestClassifier(n_estimators=200,max_depth=10,
        min_samples_split=5,min_samples_leaf=2,random_state=42,n_jobs=-1)
    rf.fit(Xtr,ytr)
    ra=accuracy_score(yte,rf.predict(Xte))
    print(f"  RF={ra:.3f}")
    print("  Neural Network...")
    nn_m,_=train_nn(Xtr,ytr,Xv,yv)
    with torch.no_grad():na=accuracy_score(yte,nn_m(torch.FloatTensor(Xte)).argmax(dim=1).numpy())
    print(f"  NN={na:.3f}")
    xp=xgb.predict_proba(Xte);rp=rf.predict_proba(Xte)
    with torch.no_grad():np_=torch.softmax(nn_m(torch.FloatTensor(Xte)),dim=1).numpy()
    ea=accuracy_score(yte,((xp+rp+np_)/3).argmax(axis=1))
    print(f"  ENS={ea:.3f}")
    return {'xgb_model':xgb,'rf_model':rf,'nn_model':nn_m,'feature_names':fn,
        'atr_params':{'tp_mult':1.5,'sl_mult':1.0,'horizon':24,'avg_atr':float(atr.dropna().mean())},
        'accuracy':{'xgb':round(xa,4),'rf':round(ra,4),'nn':round(na,4),'ensemble':round(ea,4)},
        'trained_at':datetime.now().isoformat(),'data_period':'2y','n_samples':len(d)}

print("="*60)
print("ARIA v5 - RETRAINING: XGBoost + RF + Neural Network")
print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
print("="*60)
results={}
for sym,ticker in SYMBOLS.items():
    try:
        md=train_sym(sym,ticker)
        if md:
            path=f"{MODEL_PATH}/quant_engine_v3_{sym}.pkl"
            with open(path,'wb') as f:pickle.dump(md,f)
            results[sym]=md['accuracy']
            print(f"  Saved {path}")
    except Exception as e:
        print(f"  {sym} FAILED: {e}")
print("\n"+"="*60)
print("COMPLETE")
for sym,acc in results.items():
    print(f"  {sym}: XGB={acc['xgb']:.3f} RF={acc['rf']:.3f} NN={acc['nn']:.3f} ENS={acc['ensemble']:.3f}")
print("="*60)
