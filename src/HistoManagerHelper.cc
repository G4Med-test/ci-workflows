#include "HistoManagerHelper.hh"
#include "HistoManagerMessenger.hh"

HistoManagerHelper* HistoManagerHelper::instance = nullptr;

HistoManagerHelper* HistoManagerHelper::Instance()
{
  if(instance==nullptr)
    {
      instance = new HistoManagerHelper();	
    }
  return instance;
}

HistoManagerHelper::HistoManagerHelper() :
  fFileName("out.root")
{
  fMessenger = new HistoManagerMessenger(this);
}

HistoManagerHelper::~HistoManagerHelper()
{
  if(fMessenger)
    delete fMessenger;
}
