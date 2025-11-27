#include "TreeManagerHelper.hh"
#include "TreeManagerMessenger.hh"

TreeManagerHelper* TreeManagerHelper::instance = nullptr;

TreeManagerHelper* TreeManagerHelper::Instance()
{
  if(instance==nullptr)
    {
      instance = new TreeManagerHelper();	
    }
  return instance;
}

TreeManagerHelper::TreeManagerHelper() :
  fFileName("out.root")
{
  fMessenger = new TreeManagerMessenger(this);
}

TreeManagerHelper::~TreeManagerHelper()
{
  if(fMessenger)
    delete fMessenger;
}
