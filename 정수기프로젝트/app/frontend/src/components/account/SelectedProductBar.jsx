import React from 'react';
import Icon from '../shared/Icon.jsx';
import { useCustomerProduct } from '../../context/CustomerProductContext.jsx';

const SelectedProductBar = ({ onChangeProduct,onDisconnect,disabled=false }) => {
  const { selectedProduct } = useCustomerProduct();

  if (!selectedProduct) {
    return null;
  }

  return (
    <div className="selected-product-bar"><span className="selected-product-icon"><Icon name="water"/></span>
      <div>
        <small>현재 상담 제품</small>

        <strong>
          {selectedProduct.productName}
        </strong>

        <span>
          {selectedProduct.serviceType === 'subscription'
            ? '구독'
            : '구매'}
        </span>

        {selectedProduct.contract?.careType && (
          <span>
            · {selectedProduct.contract.careType}
          </span>
        )}
      </div>

      <button
        type="button" disabled={disabled}
        onClick={onChangeProduct}
      >
        조회 범위 변경
      </button>
      <button type="button" disabled={disabled} onClick={onDisconnect}>계약 연결 해제</button>
    </div>
  );
};

export default SelectedProductBar;